from tools.risk_rules import market_risk_score, risk_capacity, suitability_gap


def test_original_market_formula_is_preserved():
    out = market_risk_score({"rsi": 50, "volatility": 4, "trend": "Uptrend"})
    assert out["riskScore"] == 27 and out["riskLevel"] == "Medium"
    assert any("High volatility" in f for f in out["riskFactors"])


def test_weak_fundamentals_and_bad_news_add_risk():
    m = {"rsi": 50, "volatility": 2, "trend": "Uptrend"}
    base = market_risk_score(m)["riskScore"]
    worse = market_risk_score(m, {"healthScore": 30}, {"sentimentScore": -1})["riskScore"]
    assert worse == base + 15


def test_capacity_extremes():
    assert risk_capacity({"age": 25, "experience": "Experienced", "riskAppetite": "Aggressive",
                          "timeHorizon": "Long-term"}) == 100
    assert risk_capacity({"age": 65, "experience": "Beginner", "riskAppetite": "Conservative",
                          "timeHorizon": "Short-term"}) == 5


def test_suitability_gap_sign():
    assert suitability_gap(40, 10) > 0
    assert suitability_gap(10, 90) < 0
