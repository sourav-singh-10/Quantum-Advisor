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
    elif age >= 60:
        score -= 20
    elif age >= 50:
        score -= 10
    score += {"Experienced": 15, "Intermediate": 5}.get(profile.get("experience"), -5)
    score += {"Aggressive": 10, "Conservative": -10}.get(profile.get("riskAppetite"), 0)
    score += {"Long-term": 15, "Short-term": -10}.get(profile.get("timeHorizon"), 0)
    return max(0, min(100, score))


def market_risk_score(market: dict, fundamentals: dict | None = None,
                      sentiment: dict | None = None, document: dict | None = None,
                      conflicts: list | None = None) -> dict:
    """Stock risk 5-100. The market part is the original RiskAgent formula; fundamentals
    and news add or remove points only when that data exists.

    ``riskBreakdown`` lists where every point came from, so the UI can chart it."""
    parts: list[dict] = []
    factors: list[str] = []

    def add(points: int, label: str, factor: str | None = None):
        parts.append({"label": label, "points": points})
        if factor:
            factors.append(factor)

    vol, rsi, trend = market["volatility"], market["rsi"], market["trend"]
    # Most NSE large caps move 1-2.5% a day, so that band is split rather than lumped.
    if vol > 3:
        add(20, "Volatility", f"High volatility ({vol:.1f}% daily)")
    elif vol > 1.8:
        add(12, "Volatility", f"Above-average volatility ({vol:.1f}% daily)")
    elif vol > 1.2:
        add(8, "Volatility")
    else:
        add(5, "Volatility")
    if rsi > 75:
        add(12, "Momentum", f"Strongly overbought (RSI {rsi:.0f})")
    elif rsi > 70:
        add(10, "Momentum", f"Overbought (RSI {rsi:.0f})")
    elif rsi < 30:
        add(8, "Momentum", f"Oversold (RSI {rsi:.0f})")
    else:
        add(4, "Momentum")
    if trend == "Downtrend":
        add(10, "Trend", "Downtrend")
    elif trend == "Sideways":
        add(6, "Trend", "Sideways market")
    else:
        add(3, "Trend")
    dd = market.get("maxDrawdownPct")
    if dd is not None and dd < -25:
        add(6, "Drawdown", f"Fell {abs(dd):.0f}% from a peak in the last six months")
    move = market.get("change1mPct")
    if move is not None and abs(move) > 8:
        add(5, "Sharp move", f"Sharp one-month move ({move:+.1f}%)")
    if fundamentals and fundamentals.get("healthScore") is not None:
        health = fundamentals["healthScore"]
        if health < 40:
            add(10, "Fundamentals", f"Weak fundamentals ({health}/100)")
        elif health >= 70:
            add(-3, "Fundamentals")
    if sentiment and sentiment.get("sentimentScore") == -1:
        add(5, "News", "Negative news flow")
    if document and document.get("documentAboutCompany") is not False:
        flags = document.get("documentRedFlags") or []
        if flags:
            add(min(16, 8 * len(flags)), "Document red flags")
            factors.extend(f"Document: {f}" for f in flags[:2])
    if document and document.get("documentAboutCompany") is False:
        factors.append("The uploaded document may be about a different company")
    elif conflicts:
        add(4, "Document conflict", "Document figures disagree with live data")
    risk = max(5, min(100, sum(p["points"] for p in parts)))
    level = "Low-Medium" if risk < 20 else "Medium" if risk < 32 else "High"
    return {"riskScore": risk, "riskLevel": level, "riskFactors": factors,
            "riskBreakdown": parts}


def suitability_gap(risk_score: int, capacity: int) -> int:
    """Positive = the stock is riskier than this investor can comfortably hold.
    Risk scores run roughly 5-50, capacity 0-100, so capacity is scaled to the same range."""
    tolerance = 12 + capacity * 0.3   # capacity 0 -> 12, 50 -> 27, 100 -> 42
    return round(risk_score - tolerance)
