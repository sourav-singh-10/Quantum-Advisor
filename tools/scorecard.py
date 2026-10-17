"""A plain scorecard of the analysis: five 0-10 scores, an entry-point verdict and red flags.

It only re-reads numbers the analysts already produced, so it cannot disagree with them; it
makes them quicker to scan. A dimension without data is left out rather than guessed.
"""
from __future__ import annotations

from typing import Optional


def _clamp(x: float) -> int:
    return int(round(max(0.0, min(10.0, x))))


def _num(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _momentum(d: dict):
    trend, m1 = d.get("trend"), _num(d.get("change1mPct"))
    if trend is None and m1 is None:
        return None
    s = 5.0 + {"Uptrend": 2, "Downtrend": -2}.get(trend, 0)
    if m1 is not None:
        s += max(-2.0, min(2.0, m1 / 4))
    macd = (d.get("macdState") or "").lower()
    s += 1 if macd.startswith("bullish") else -1 if macd.startswith("bearish") else 0
    why = f"{trend or 'No clear trend'}" + (f", {m1:+.1f}% in a month" if m1 is not None else "")
    if macd:
        why += f", MACD {macd}"
    return _clamp(s), why


def _valuation(d: dict):
    pe = _num(d.get("pe"))
    if pe is None:
        return None
    if pe <= 0:
        return 1, "Loss-making, so the P/E is not meaningful"
    s = 8 if pe <= 12 else 7 if pe <= 20 else 5 if pe <= 30 else 3 if pe <= 45 else 2
    return s, f"P/E {pe:.1f}" + (" (cheap)" if s >= 7 else " (fair)" if s == 5 else " (expensive)")


def _profitability(d: dict):
    roe, margin = _num(d.get("roe")), _num(d.get("profitMargin"))
    if roe is None and margin is None:
        return None
    parts, s = [], 0.0
    if roe is not None:
        s += max(0.0, min(6.0, roe / 25 * 6)); parts.append(f"ROE {roe:.0f}%")
    if margin is not None:
        s += max(0.0, min(4.0, margin / 25 * 4)); parts.append(f"margin {margin:.0f}%")
    if roe is None or margin is None:          # rescale when only one figure is known
        s *= 10 / (6 if roe is not None else 4)
    return _clamp(s), ", ".join(parts)


def _health(d: dict):
    h = _num(d.get("healthScore"))
    if h is None or d.get("fundamentalsAvailable") is False:
        return None
    de = _num(d.get("de"))
    return _clamp(h / 10), (d.get("financialHealth") or "Health score") + (f", debt/equity {de:.1f}" if de is not None else "")


def _news(d: dict):
    if d.get("newsAvailable") is False or d.get("newsSentiment") in (None, "Not analysed"):
        return None
    s = {1: 8, 0: 5, -1: 2}.get(int(_num(d.get("sentimentScore")) or 0), 5)
    n = d.get("headlineCount") or 0
    return s, f"{d.get('newsSentiment')} across {n} headline{'s' if n != 1 else ''}"


def entry_point(d: dict) -> dict:
    rsi, pb = _num(d.get("rsi")), _num(d.get("bbPercentB"))
    to_sup = _num(d.get("toSupportPct"))
    if (rsi is not None and rsi >= 70) or (pb is not None and pb > 1):
        return {"verdict": "Stretched", "why": "Price is high in its recent range; entries after a run-up often see a pullback."}
    if (rsi is not None and rsi <= 35) or (pb is not None and pb < 0.2) or (to_sup is not None and to_sup > -3):
        return {"verdict": "Good", "why": "Price is near the low end of its recent range."}
    return {"verdict": "Fair", "why": "Price is mid-range: neither stretched nor near support."}


def red_flags(d: dict) -> list[str]:
    flags = []
    rsi, vol, de, pe = (_num(d.get(k)) for k in ("rsi", "volatility", "de", "pe"))
    if rsi is not None and rsi >= 75:
        flags.append(f"Deeply overbought (RSI {rsi:.0f})")
    if vol is not None and vol > 2.5:
        flags.append(f"Very volatile ({vol:.1f}% a day)")
    if de is not None and de > 2:
        flags.append(f"High debt (debt/equity {de:.1f})")
    if pe is not None and pe <= 0:
        flags.append("Company is loss-making")
    dd = _num(d.get("maxDrawdownPct"))
    if dd is not None and dd <= -30:
        flags.append(f"Fell {abs(dd):.0f}% at its worst in six months")
    if d.get("sentimentScore") == -1 and d.get("materialHeadlines"):
        flags.append("Negative news that may move the price")
    if d.get("documentConflicts"):
        flags.append("The uploaded report disagrees with market data")
    return flags


def scorecard(d: dict) -> dict:
    dims = [("Momentum", _momentum), ("Valuation", _valuation), ("Profitability", _profitability),
            ("Financial health", _health), ("News", _news)]
    scores = []
    for name, fn in dims:
        r = fn(d)
        if r is not None:
            scores.append({"name": name, "score": r[0], "why": r[1]})
    return {"scores": scores, "entry": entry_point(d), "redFlags": red_flags(d)}
