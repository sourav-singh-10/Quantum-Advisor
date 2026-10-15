"""Company fundamentals (yfinance) plus a transparent rule-based health score."""
from __future__ import annotations

from tools.base import ToolError, cached


def fetch_fundamentals(symbol: str) -> dict:
    def _load():
        try:
            import yfinance as yf
            info = yf.Ticker(f"{symbol}.NS").info or {}
        except Exception as exc:
            raise ToolError(f"yfinance error: {type(exc).__name__}") from exc
        out = {
            "pe": info.get("trailingPE"),
            "roe": _pct(info.get("returnOnEquity")),
            "de": _ratio(info.get("debtToEquity")),
            "profitMargin": _pct(info.get("profitMargins")),
            "sector": info.get("sector"),
            "marketCapCr": round(info["marketCap"] / 1e7) if info.get("marketCap") else None,
            "name": info.get("longName") or info.get("shortName"),
        }
        if all(out[k] is None for k in ("pe", "roe", "de", "profitMargin")):
            raise ToolError(f"no fundamentals available for {symbol}.NS")
        return out

    return cached(("fundamentals", symbol), _load)


def _pct(v):
    return round(float(v) * 100, 2) if v is not None else None


def _ratio(v):
    # yfinance reports debt/equity as a percentage (e.g. 45.3 means 0.453)
    return round(float(v) / 100, 2) if v is not None else None


def score_fundamentals(f: dict) -> dict:
    """Rule-based score 0-100. Missing metrics count as neutral and are listed."""
    score, notes, missing = 50, [], []
    pe, roe, de, margin = f.get("pe"), f.get("roe"), f.get("de"), f.get("profitMargin")
    if pe is None:
        missing.append("PE")
    elif pe < 0:
        score -= 15; notes.append("negative earnings")
    elif pe < 25:
        score += 10; notes.append(f"reasonable PE {pe:.1f}")
    elif pe > 60:
        score -= 10; notes.append(f"expensive PE {pe:.1f}")
    if roe is None:
        missing.append("ROE")
    elif roe >= 15:
        score += 15; notes.append(f"strong ROE {roe:.1f}%")
    elif roe < 8:
        score -= 10; notes.append(f"weak ROE {roe:.1f}%")
    if de is None:
        missing.append("D/E")
    elif de > 2:
        score -= 15; notes.append(f"high debt/equity {de:.2f}")
    elif de < 0.5:
        score += 10; notes.append(f"low debt/equity {de:.2f}")
    if margin is not None and margin < 0:
        score -= 10; notes.append("loss-making")
    score = max(0, min(100, score))
    label = "Strong" if score >= 70 else "Stable" if score >= 50 else "Weak"
    return {"healthScore": score, "financialHealth": label, "notes": notes, "missing": missing}
