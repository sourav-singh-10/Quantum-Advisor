"""Price-history tools. Each returns closing prices oldest -> newest or raises ToolError."""
from __future__ import annotations

import config
from tools.base import ToolError, cached, http_get_json

# Free-tier order: yfinance (no key, no fixed quota) -> Alpha Vantage (25 calls/day)
# -> MarketStack (100 calls/month). The agent may choose differently after a failure.
SOURCES = ("yfinance", "alphavantage", "marketstack")


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
    return [float(x) for x in hist["Close"].dropna().tolist()]


_FETCHERS = {
    "marketstack": fetch_marketstack,
    "alphavantage": fetch_alphavantage,
    "yfinance": fetch_yfinance,
}


def get_price_history(symbol: str, source: str) -> list[float]:
    source = (source or "").lower().strip()
    if source not in _FETCHERS:
        raise ToolError(f"unknown source '{source}'; choose one of {', '.join(SOURCES)}")
    prices = cached(("prices", source, symbol), lambda: _FETCHERS[source](symbol))
    if len(prices) < 20:
        raise ToolError(f"{source} returned only {len(prices)} prices; need at least 20")
    return prices
