
from agents.risk_agent import RiskAgent


def test_high_volatility_increases_risk():
    agent = RiskAgent()

    market = {
        "rsi": 50,
        "volatility": 4,
        "trend": "Uptrend",
    }

    result = agent.analyze({}, market, {})

    assert result["riskScore"] == 27
    assert result["riskLevel"] == "Medium"
    assert "High volatility" in result["riskFactors"]


def test_risk_agent_requests_review_for_risky_buy():
    agent = RiskAgent()

    strategy = {"recommendation": "BUY"}
    risk = {"riskScore": 30}

    review = agent.review_strategy(strategy, risk)

    assert review["needsRevision"] is True


def test_risk_agent_does_not_request_review_for_low_risk_buy():
    agent = RiskAgent()

    strategy = {"recommendation": "BUY"}
    risk = {"riskScore": 15}

    review = agent.review_strategy(strategy, risk)

    assert review["needsRevision"] is False
