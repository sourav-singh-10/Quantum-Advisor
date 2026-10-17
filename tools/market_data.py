"""Price-history tools. Each returns closing prices oldest -> newest or raises ToolError."""
from __future__ import annotations

import config
from tools.base import ToolError, cached, http_get_json

# Free-tier order: yfinance (no key, no fixed quota) -> Alpha Vantage (25 calls/day)
# -> MarketStack (100 calls/month). The agent may choose differently after a failure.
SOURCES = ("yfinance", "alphavantage", "marketstack")

# NSE symbols that changed after a merger or rename; users still type the old one.
RENAMED = {
    "ZOMATO": "ETERNAL",      # Zomato Ltd renamed Eternal Ltd (2025)
    "HDFC": "HDFCBANK",       # HDFC Ltd merged into HDFC Bank (July 2023)
    "MINDTREE": "LTIM",       # merged into LTIMindtree (2022)
    "LTI": "LTIM",
}


def fetch_marketstack(symbol: str) -> list[float]:
    if not config.MARKETSTACK_API_KEY:
        raise ToolError("MARKETSTACK_API_KEY not configured")
    # MarketStack's free plan only serves plain http.
    data = http_get_json("http://api.marketstack.com/v1/eod",
                         {"access_key": config.MARKETSTACK_API_KEY,
                          "symbols": f"{symbol}.XNSE", "limit": 120})
    if data.get("error"):
        raise ToolError(f"MarketStack: {data['error'].get('message', 'error')}")
    rows = data.get("data") or []
    if not rows:
        raise ToolError(f"MarketStack returned no rows for {symbol}")
    return [float(r["close"]) for r in reversed(rows) if r.get("close") is not None]


def fetch_alphavantage(symbol: str) -> list[float]:
    if not config.ALPHAVANTAGE_API_KEY:
        raise ToolError("ALPHAVANTAGE_API_KEY not configured")
    data = http_get_json("https://www.alphavantage.co/query",
                         {"function": "TIME_SERIES_DAILY", "symbol": f"{symbol}.BSE",
                          "apikey": config.ALPHAVANTAGE_API_KEY})
    series = data.get("Time Series (Daily)")
    if not series:
        note = data.get("Note") or data.get("Information") or data.get("Error Message")
        raise ToolError(f"Alpha Vantage: {note or 'no data'}"[:200])
    return [float(series[d]["4. close"]) for d in sorted(series)]


def fetch_yfinance(symbol: str) -> list[float]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ToolError("yfinance not installed") from exc
    try:
        hist = yf.Ticker(f"{symbol}.NS").history(period="6mo", interval="1d")
    except Exception as exc:
        raise ToolError(f"yfinance error: {type(exc).__name__}") from exc
    if hist is None or hist.empty:
        raise ToolError(f"yfinance returned no rows for {symbol}.NS")
    hist = hist[hist["Close"].notna()]
    if "Volume" in hist:
        # Keep volumes and dates from the same download: the volume check and the chart's
        # date axis cost no extra request.
        cached(("volume", symbol), lambda: [float(v) for v in hist["Volume"].fillna(0).tolist()],
               ttl=0)
    try:
        cached(("dates", symbol), lambda: [d.strftime("%Y-%m-%d") for d in hist.index], ttl=0)
    except AttributeError:
        pass
    return [float(x) for x in hist["Close"].tolist()]


_FETCHERS = {
    "marketstack": fetch_marketstack,
    "alphavantage": fetch_alphavantage,
    "yfinance": fetch_yfinance,
}


def chart_series(symbol: str, n: int) -> dict:
    """Dates and volumes for the last n closes, when the source provided them (yfinance)."""
    from tools.base import _cache, _cache_lock
    with _cache_lock:
        dates = (_cache.get(("dates", symbol)) or (0, None))[1]
        vols = (_cache.get(("volume", symbol)) or (0, None))[1]
    out = {}
    if dates and len(dates) >= n:
        out["priceDates"] = dates[-n:]
    if vols and len(vols) >= n:
        out["volumeHistory"] = [round(v) for v in vols[-n:]]
    return out


def volume_signal(symbol: str) -> dict:
    """Recent trading volume against its 50-day average (yfinance only)."""
    from tools.base import _cache, _cache_lock
    with _cache_lock:
        hit = _cache.get(("volume", symbol))
    volumes = hit[1] if hit else None
    if not volumes:
        raise ToolError("volume is only available when prices came from yfinance")
    volumes = [v for v in volumes if v > 0]
    if len(volumes) < 25:
        raise ToolError("not enough volume data")
    recent = sum(volumes[-5:]) / 5
    base = sum(volumes[-50:]) / len(volumes[-50:])
    ratio = recent / base if base else 1.0
    label = "High" if ratio > 1.5 else "Low" if ratio < 0.6 else "Normal"
    return {"volumeRatio": round(ratio, 2), "volumeLevel": label,
            "avgVolume50": round(base)}


def get_price_history(symbol: str, source: str) -> list[float]:
    source = (source or "").lower().strip()
    if source not in _FETCHERS:
        raise ToolError(f"unknown source '{source}'; choose one of {', '.join(SOURCES)}")
    prices = cached(("prices", source, symbol), lambda: _FETCHERS[source](symbol))
    if len(prices) < 20:
        raise ToolError(f"{source} returned only {len(prices)} prices; need at least 20")
    return prices
