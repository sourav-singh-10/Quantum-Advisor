
import json
from datetime import datetime, timezone
from pathlib import Path

from legacy.agents.market_agent import MarketAgent
from legacy.agents.fundamentals_agent import FundamentalsAgent
from legacy.agents.risk_agent import RiskAgent
from legacy.agents.strategy_agent import StrategyAgent
from legacy.agents.portfolio_agent import PortfolioAgent
from legacy.agents.user_agent import UserAgent
from legacy.agents.report_agent import ReportAgent
from legacy.agents.news_sentiment_agent import NewsSentimentAgent


class Orchestrator:

    def __init__(self):
        self.market = MarketAgent()
        self.fund = FundamentalsAgent()
        self.risk = RiskAgent()
        self.strategy = StrategyAgent()
        self.portfolio = PortfolioAgent()
        self.user = UserAgent()
        self.report = ReportAgent()
        self.sentiment = NewsSentimentAgent()

        self.log_dir = Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trace_file = self.log_dir / "agent_trace.jsonl"

    def trace(self, agent, event, ticker, details=None):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "agent": agent,
            "event": event,
            "details": details or {},
        }

        with self.trace_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, default=str) + "\n")

    def analyze(self, ticker, user):

        self.trace("Orchestrator", "run_started", ticker)

        # 1. User profiling
        u = self.user.analyze(user)
        self.trace("UserAgent", "completed", ticker)

        # 2. Market analysis
        m = self.market.analyze(ticker)
        self.trace(
            "MarketAgent", "completed", ticker,
            {"trend": m.get("trend")}
        )

        # 3. Fundamentals
        f = self.fund.analyze(ticker)
        self.trace("FundamentalsAgent", "completed", ticker)

        # 4. News sentiment
        sent = self.sentiment.analyze(ticker)
        self.trace(
            "NewsSentimentAgent", "completed", ticker,
            {"newsSentiment": sent.get("newsSentiment")}
        )

        # 5. Initial risk assessment
        r = self.risk.analyze(user, m, f)
        self.trace(
            "RiskAgent", "risk_assessed", ticker,
            {"riskScore": r["riskScore"], "riskLevel": r["riskLevel"]}
        )

        # 6. Initial strategy
        s = self.strategy.analyze(user, m, f, r, sent)
        self.trace(
            "StrategyAgent", "initial_recommendation", ticker,
            {"recommendation": s["recommendation"]}
        )

        # 7. Risk reviews the strategy; branch depends on its result
        review = self.risk.review_strategy(s, r)
        self.trace(
            "RiskAgent", "strategy_reviewed", ticker, review
        )

        if review["needsRevision"]:
            self.trace(
                "Orchestrator", "revision_requested", ticker,
                {"reason": review["reason"]}
            )

            # One bounded revision attempt
            s = self.strategy.analyze(
                user, m, f, r, sent, feedback=review
            )

            self.trace(
                "StrategyAgent", "revised_recommendation", ticker,
                {"recommendation": s["recommendation"]}
            )

        # 8. Portfolio advice uses the final strategy
        p = self.portfolio.analyze(user, m, s)
        self.trace("PortfolioAgent", "completed", ticker)

        # 9. Report
        rep = self.report.analyze(ticker, m, r, sent)
        self.trace("ReportAgent", "completed", ticker)
        self.trace("Orchestrator", "run_completed", ticker)

        return {
            **u,
            **m,
            **f,
            **sent,
            **r,
            **s,
            **p,
            **rep,
            "riskReview": review,
        }
