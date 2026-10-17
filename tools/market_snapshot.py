"""One-call daily snapshot of a stock for the briefs: last price, day move, 52-week range,
volume against normal, trend and RSI. yfinance first (it has dates and volume), then the
other price sources as a fallback without those extras."""
from __future__ import annotations

from tools import market_data
from tools.base import ToolError, cached
from tools.indicators import compute_indicators

SNAPSHOT_TTL = 600     # seconds; briefs for many users share one download per stock


def _yf_year(symbol: str):
    def _load():
        try:
            import yfinance as yf
            hist = yf.Ticker(f"{symbol}.NS").history(period="1y", interval="1d")
        except Exception as exc:
            raise ToolError(f"yfinance error: {type(exc).__name__}") from exc
        if hist is None or hist.empty:
            raise ToolError(f"yfinance returned no rows for {symbol}.NS")
        hist = hist[hist["Close"].notna()]
        closes = [float(x) for x in hist["Close"].tolist()]
        vols = [float(v) for v in hist["Volume"].fillna(0).tolist()] if "Volume" in hist else []
        try:
            dates = [d.strftime("%Y-%m-%d") for d in hist.index]
        except AttributeError:
            dates = []
        return closes, vols, dates
    return cached(("year", symbol), _load, ttl=SNAPSHOT_TTL)


def _pct(a: float, b: float) -> float | None:
    return round((a / b - 1) * 100, 2) if b else None


def snapshot(symbol: str) -> dict:
    """Raises ToolError when no source has prices for the symbol."""
    symbol = market_data.RENAMED.get(symbol, symbol)
    closes, vols, dates, source = [], [], [], None
    try:
        closes, vols, dates = _yf_year(symbol)
        source = "yfinance"
    except ToolError as first:
        for src in market_data.SOURCES:
            if src == "yfinance":
                continue
            try:
                closes, source = market_data.get_price_history(symbol, src), src
                break
            except ToolError:
                continue
        if not closes:
            raise first
    if len(closes) < 20:
        raise ToolError(f"only {len(closes)} prices for {symbol}")

    ind = compute_indicators(closes)
    last, prev = closes[-1], closes[-2]
    year = closes[-250:]
    out = {
        "ticker": symbol, "price": round(last, 2), "prevClose": round(prev, 2),
        "changePct": _pct(last, prev),
        "change5dPct": _pct(last, closes[-6]) if len(closes) > 6 else None,
        "change1mPct": _pct(last, closes[-22]) if len(closes) > 22 else None,
        "high52": round(max(year), 2), "low52": round(min(year), 2),
        "rangeLabel": "52-week" if len(year) >= 200 else f"{len(year)}-day",
        "trend": ind["trend"], "rsi": round(ind["rsi"], 1), "volatility": round(ind["volatility"], 2),
        "source": source, "asOf": dates[-1] if dates else None,
        "history": [round(x, 2) for x in closes[-30:]],
    }
    out["fromHighPct"] = _pct(last, out["high52"])
    out["fromLowPct"] = _pct(last, out["low52"])
    good = [v for v in vols if v > 0]
    if len(good) >= 21 and vols[-1] > 0:
        base = sum(good[-21:-1]) / 20
        out["volumeRatio"] = round(vols[-1] / base, 2) if base else None
    else:
        out["volumeRatio"] = None
    return out
