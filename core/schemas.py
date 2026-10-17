"""Pydantic schemas for (1) the API request and (2) every structured LLM decision.

Keeping the LLM's answers typed is what lets agents argue reliably: a critique always has
objection ids, a draft always says which objections it answered.
"""
from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------- API request
TICKER_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")


class Goal(BaseModel):
    """Something the investor is saving for."""
    title: str = Field(min_length=1, max_length=80)
    amount: Optional[float] = Field(None, ge=0, le=1e11)
    year: Optional[int] = Field(None, ge=2025, le=2100)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("give the goal a name")
        return v


class InvestorProfile(BaseModel):
    """The investor's standing details; saved per account and pre-filled in the app."""
    name: Optional[str] = Field(None, max_length=40)
    age: int = Field(30, ge=18, le=100)
    experience: Literal["Beginner", "Intermediate", "Experienced"] = "Beginner"
    riskAppetite: Literal["Conservative", "Moderate", "Aggressive"] = "Moderate"
    portfolioValue: float = Field(50000, gt=0, le=1e11)
    timeHorizon: Literal["Short-term", "Medium-term", "Long-term"] = "Medium-term"
    goal: Optional[str] = Field(None, max_length=300)
    goals: List[Goal] = Field(default_factory=list, max_length=4)
    monthlyInvest: Optional[float] = Field(None, ge=0, le=1e9)
    avoidSectors: List[str] = Field(default_factory=list, max_length=8)

    @field_validator("avoidSectors")
    @classmethod
    def known_avoid_options(cls, v: list[str]) -> list[str]:
        from tools.preferences import AVOID_OPTIONS
        unknown = [x for x in v if x not in AVOID_OPTIONS]
        if unknown:
            raise ValueError(f"choose from: {', '.join(AVOID_OPTIONS)}")
        return list(dict.fromkeys(v))

    def goals_text(self) -> str:
        """The goals in one line, for the agents."""
        parts = []
        for g in self.goals:
            bits = [g.title]
            if g.amount:
                bits.append(f"INR {g.amount:,.0f}")
            if g.year:
                bits.append(f"by {g.year}")
            parts.append(" ".join(bits))
        return "; ".join(parts)


class AnalyzeRequest(InvestorProfile):
    ticker: str
    # Does the investor already own it? None: the server checks the saved holdings.
    holding: Optional[bool] = None

    @field_validator("ticker")
    @classmethod
    def clean_ticker(cls, v: str) -> str:
        v = (v or "").strip().upper()
        for suffix in (".NS", ".BO", ".NSE", ".BSE"):
            if v.endswith(suffix):
                v = v[: -len(suffix)]
        if not TICKER_RE.match(v):
            raise ValueError("ticker must be 1-20 characters: letters, digits, & or -")
        return v


# ---------------------------------------------------------------- Planner
AnalystName = Literal["MarketAnalyst", "FundamentalsAnalyst", "NewsAnalyst", "DocumentAnalyst"]


class PlanTask(BaseModel):
    agent: AnalystName
    instruction: str = Field(description="What this analyst should focus on for this request")


class Plan(BaseModel):
    reasoning: str = Field(description="Why these analysts, in 1-3 sentences")
    tasks: List[PlanTask]
    focus: str = Field(description="The single most important question for this investor")


class RetryTask(BaseModel):
    agent: AnalystName
    instruction: str = Field(description="What to do differently, e.g. which data source to try")


class Assessment(BaseModel):
    reasoning: str
    action: Literal["proceed", "retry"]
    retries: List[RetryTask] = Field(default_factory=list)
    confidence_cap: Literal["Low", "Moderate", "High"] = Field(
        description="Highest confidence the final recommendation may claim given data quality")


class Arbitration(BaseModel):
    reasoning: str
    recommendation: Literal["BUY", "HOLD", "SELL"]
    confidence: Literal["Low", "Moderate", "High"]


# ---------------------------------------------------------------- Tool loop step
class ToolStep(BaseModel):
    thought: str = Field(description="Reasoning about what to do next, given observations so far")
    action: str = Field(description="Name of the tool to call, or 'finish'")
    argument: str = Field("", description="Single argument for the tool (e.g. a data source)")


# ---------------------------------------------------------------- Analysts
class ProfileView(BaseModel):
    summary: str = Field(description="One sentence describing this investor")
    max_position_pct: float = Field(description="Largest % of portfolio for one stock, 1-15")
    horizon_years: float
    constraints: List[str] = Field(description="Constraints implied by the profile or goal")


class MarketView(BaseModel):
    summary: str = Field(description="2 sentences interpreting trend, RSI and volatility together")
    momentum: Literal["Strong up", "Up", "Flat", "Down", "Strong down"]
    data_quality: Literal["Good", "Limited", "Poor"]


class FundamentalsView(BaseModel):
    summary: str
    financialHealth: Literal["Strong", "Stable", "Weak", "Unknown"]
    key_points: List[str]


# ---------------------------------------------------------------- Document analyst
class DocumentFigures(BaseModel):
    """Figures exactly as printed in the document, for the latest period it reports."""
    period: Optional[str] = Field(None, description="e.g. 'Q2 FY27' or 'FY 2025-26'")
    unit: Optional[str] = Field(None, description="Unit the money figures are printed in, e.g. 'crore'")
    revenue: Optional[float] = None
    netProfit: Optional[float] = None
    eps: Optional[float] = Field(None, description="Basic EPS in rupees")
    borrowings: Optional[float] = None
    equity: Optional[float] = None


class DocumentFindings(BaseModel):
    about_company: bool = Field(description="False if the document is about a different company")
    figures: DocumentFigures
    key_points: List[str] = Field(description="2-4 facts from the document that matter to an investor")
    red_flags: List[str] = Field(default_factory=list,
                                 description="Audit qualifications, defaults, going-concern doubts")
    summary: str


class Reconciliation(BaseModel):
    reasoning: str
    trust: Literal["document", "live", "both"] = Field(
        description="Which figures the team should rely on where they differ")
    confidence_cap: Literal["Low", "Moderate", "High"]


class HeadlineLabel(BaseModel):
    index: int
    sentiment: Literal["Positive", "Neutral", "Negative"]
    material: bool = Field(description="True if the headline could move the share price")


class NewsView(BaseModel):
    labels: List[HeadlineLabel]
    overall: Literal["Positive", "Neutral", "Negative"]
    summary: str


# ---------------------------------------------------------------- Risk <-> Strategy
class RiskView(BaseModel):
    summary: str
    key_risks: List[str]
    suitable_for_investor: bool


class Objection(BaseModel):
    id: str = Field(description="Stable id like R1, R2")
    text: str
    severity: Literal["minor", "major", "blocking"]


class FollowUpRequest(BaseModel):
    """A request, sent through the Planner, for one more piece of evidence from an analyst."""
    agent: AnalystName = Field(description="The analyst who can answer")
    question: str = Field(description="One specific question, e.g. 'Is the SEBI headline about this "
                                      "company?' or 'How does the last year look, not just 3 months?'")
    why: str = Field("", description="How the answer could change the decision")


class Critique(BaseModel):
    verdict: Literal["approve", "revise", "veto"]
    reasoning: str
    objections: List[Objection] = Field(default_factory=list)
    followup: Optional[FollowUpRequest] = Field(
        None, description="Ask for ONE more piece of evidence before the next round, only when the "
                          "answer could change your verdict. Leave empty otherwise.")


class ObjectionResponse(BaseModel):
    objection_id: str
    response: str


class StrategyDraft(BaseModel):
    recommendation: Literal["BUY", "HOLD", "SELL"]
    confidence: Literal["Low", "Moderate", "High"]
    rationale: List[str] = Field(description="3-5 short reasons, citing the analysts' numbers")
    responses: List[ObjectionResponse] = Field(default_factory=list)
    followup: Optional[FollowUpRequest] = Field(
        None, description="Ask for ONE more piece of evidence before you commit, only if an answer "
                          "could change your call. Leave empty otherwise.")


class FollowUpGrant(BaseModel):
    """The Planner's ruling on a follow-up request."""
    grant: bool
    agent: AnalystName
    instruction: str = Field(description="The exact task for the analyst")
    reasoning: str


class FollowUpAnswer(BaseModel):
    answer: str = Field(description="A direct answer to the question in 1-3 sentences, with numbers")
    evidence: List[str] = Field(default_factory=list, description="The facts relied on")
    changes_view: bool = Field(description="True if this should change the team's earlier view")


# ---------------------------------------------------------------- Portfolio & report
class PortfolioAdvice(BaseModel):
    advice: List[str] = Field(description="2-4 concrete lines using the computed numbers")


class Report(BaseModel):
    headline: str
    body: str = Field(description="Plain-language report, 120-220 words, no markdown headings")


# ---------------------------------------------------------------- Portfolio review
class HoldingCall(BaseModel):
    ticker: str
    action: Literal["ADD", "HOLD", "TRIM", "REVIEW"]
    reason: str = Field(description="One short sentence citing the holding's numbers")


class PortfolioReview(BaseModel):
    summary: str = Field(description="2-3 sentences on the portfolio as a whole")
    actions: List[str] = Field(description="3-5 concrete next steps, most important first")
    holdings: List[HoldingCall]


# ---------------------------------------------------------------- watchlist briefs
class BriefSummary(BaseModel):
    headline: str = Field(description="One sentence: the single most important thing today")
    points: List[str] = Field(description="2-4 short points, each naming a stock and citing its numbers")
    actions: List[str] = Field(default_factory=list,
                               description="0-3 things to check or do; never a direct buy or sell order")
