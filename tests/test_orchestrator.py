
import json

from orchestrator import Orchestrator
from agents.risk_agent import RiskAgent
from agents.strategy_agent import StrategyAgent


class FakeUserAgent:
    def analyze(self, user):
        return {"userType": "Test Investor"}


class FakeMarketAgent:
    def __init__(self, volatility):
        self.volatility = volatility

    def analyze(self, ticker):
        return {
            "ticker": ticker,
            "currentPrice": 100.0,
            "priceDisplay": "₹100.00",
            "rsi": 50,
            "volatility": self.volatility,
            "trend": "Uptrend",
        }


class FakeFundamentalsAgent:
    def analyze(self, ticker):
        return {"financialHealth": "Unknown"}


class FakeSentimentAgent:
    def __init__(self, score):
        self.score = score

    def analyze(self, ticker):
        label = {
            1: "Positive",
            0: "Neutral",
            -1: "Negative",
        }[self.score]

        return {
            "sentimentScore": self.score,
            "newsSentiment": label,
            "topHeadlines": [],
        }


class FakePortfolioAgent:
    def analyze(self, user, market, strategy):
        return {"portfolioAdvice": []}


class FakeReportAgent:
    def analyze(self, ticker, market, risk, sentiment):
        return {"aiReport": "Test report"}


def make_orchestrator(tmp_path, volatility, sentiment_score):
    obj = Orchestrator.__new__(Orchestrator)

    obj.user = FakeUserAgent()
    obj.market = FakeMarketAgent(volatility)
    obj.fund = FakeFundamentalsAgent()
    obj.sentiment = FakeSentimentAgent(sentiment_score)
    obj.risk = RiskAgent()
    obj.strategy = StrategyAgent()
    obj.portfolio = FakePortfolioAgent()
    obj.report = FakeReportAgent()
    obj.trace_file = tmp_path / "agent_trace.jsonl"

    return obj


def read_trace(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_high_risk_buy_triggers_revision(tmp_path):
    # Risk = 20 volatility + 4 RSI + 3 trend = 27.
    obj = make_orchestrator(tmp_path, volatility=4, sentiment_score=1)

    result = obj.analyze("TEST", {"age": 30})

    assert result["riskReview"]["needsRevision"] is True
    assert result["recommendation"] == "HOLD"

    events = [row["event"] for row in read_trace(obj.trace_file)]

    assert "revision_requested" in events
    assert "revised_recommendation" in events
    assert events[-1] == "run_completed"


def test_low_risk_buy_does_not_trigger_revision(tmp_path):
    # Risk = 5 volatility + 4 RSI + 3 trend = 12.
    obj = make_orchestrator(tmp_path, volatility=0.5, sentiment_score=0)

    result = obj.analyze("TEST", {"age": 30})

    assert result["riskReview"]["needsRevision"] is False
    assert result["recommendation"] == "BUY"

    events = [row["event"] for row in read_trace(obj.trace_file)]

    assert "revision_requested" not in events
    assert "run_completed" in events
