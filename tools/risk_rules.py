"""Deterministic risk maths. Agents call these as tools; the LLM interprets, never invents them."""
from __future__ import annotations


def risk_capacity(profile: dict) -> int:
    """Investor's capacity to take risk, 0-100 (the original UserAgent formula)."""
    score = 50
    age = profile.get("age", 30)
    if age < 30:
        score += 20
    elif age < 40:
        score += 10
    elif age > 60:
        score -= 20
    score += {"Experienced": 15, "Intermediate": 5}.get(profile.get("experience"), -5)
    score += {"Aggressive": 10, "Conservative": -10}.get(profile.get("riskAppetite"), 0)
    score += {"Long-term": 15, "Short-term": -10}.get(profile.get("timeHorizon"), 0)
    return max(0, min(100, score))


def market_risk_score(market: dict, fundamentals: dict | None = None,
                      sentiment: dict | None = None) -> dict:
    """Stock risk 5-100. The market part is the original RiskAgent formula; fundamentals
    and news add or remove points only when that data exists."""
    risk, factors = 0, []
    vol, rsi, trend = market["volatility"], market["rsi"], market["trend"]
    if vol > 3:
        risk += 20; factors.append(f"High volatility ({vol:.1f}% daily)")
    elif vol > 1:
        risk += 10
    else:
        risk += 5
    if rsi > 70:
        risk += 10; factors.append(f"Overbought (RSI {rsi:.0f})")
    elif rsi < 30:
        risk += 8; factors.append(f"Oversold (RSI {rsi:.0f})")
    else:
        risk += 4
    if trend == "Downtrend":
        risk += 10; factors.append("Downtrend")
    elif trend == "Sideways":
        risk += 6; factors.append("Sideways market")
    else:
        risk += 3
    if fundamentals and fundamentals.get("healthScore") is not None:
        health = fundamentals["healthScore"]
        if health < 40:
            risk += 10; factors.append(f"Weak fundamentals ({health}/100)")
        elif health >= 70:
            risk -= 3
    if sentiment and sentiment.get("sentimentScore") == -1:
        risk += 5; factors.append("Negative news flow")
    risk = max(5, min(100, risk))
    level = "Low-Medium" if risk < 20 else "Medium" if risk < 32 else "High"
    return {"riskScore": risk, "riskLevel": level, "riskFactors": factors}


def suitability_gap(risk_score: int, capacity: int) -> int:
    """Positive = the stock is riskier than this investor can comfortably hold.
    Risk scores run roughly 5-50, capacity 0-100, so capacity is scaled to the same range."""
    tolerance = 12 + capacity * 0.3   # capacity 0 -> 12, 50 -> 27, 100 -> 42
    return round(risk_score - tolerance)
