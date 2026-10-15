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


class AnalyzeRequest(BaseModel):
    ticker: str
    age: int = Field(30, ge=18, le=100)
    experience: Literal["Beginner", "Intermediate", "Experienced"] = "Beginner"
    riskAppetite: Literal["Conservative", "Moderate", "Aggressive"] = "Moderate"
    portfolioValue: float = Field(50000, gt=0, le=1e11)
    timeHorizon: Literal["Short-term", "Medium-term", "Long-term"] = "Medium-term"
    goal: Optional[str] = Field(None, max_length=300)

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
AnalystName = Literal["MarketAnalyst", "FundamentalsAnalyst", "NewsAnalyst"]


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


class Critique(BaseModel):
    verdict: Literal["approve", "revise", "veto"]
    reasoning: str
    objections: List[Objection] = Field(default_factory=list)


class ObjectionResponse(BaseModel):
    objection_id: str
    response: str


class StrategyDraft(BaseModel):
    recommendation: Literal["BUY", "HOLD", "SELL"]
    confidence: Literal["Low", "Moderate", "High"]
    rationale: List[str] = Field(description="3-5 short reasons, citing the analysts' numbers")
    responses: List[ObjectionResponse] = Field(default_factory=list)


# ---------------------------------------------------------------- Portfolio & report
class PortfolioAdvice(BaseModel):
    advice: List[str] = Field(description="2-4 concrete lines using the computed numbers")


class Report(BaseModel):
    headline: str
    body: str = Field(description="Plain-language report, 120-220 words, no markdown headings")
