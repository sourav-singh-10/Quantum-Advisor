"""Technical indicators computed from closing prices (pure maths, no network)."""
from __future__ import annotations

import pandas as pd

from tools.base import ToolError


def compute_indicators(prices: list[float]) -> dict:
    if not prices or len(prices) < 20:
        raise ToolError("need at least 20 prices to compute indicators")
    series = pd.Series(prices, dtype="float64")
    price = float(series.iloc[-1])

    delta = series.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    last_loss = float(loss.iloc[-1])
    if last_loss == 0:
        rsi = 100.0
    else:
        rsi = float(100 - 100 / (1 + float(gain.iloc[-1]) / last_loss))

    volatility = float(series.pct_change().std() * 100)

    ma20 = float(series.rolling(20).mean().iloc[-1])
    if len(series) >= 50:
        ma50 = float(series.rolling(50).mean().iloc[-1])
        reference = ma50
    else:
        ma50 = None
        reference = price
    if ma20 > reference * 1.005:
        trend = "Uptrend"
    elif ma20 < reference * 0.995:
        trend = "Downtrend"
    else:
        trend = "Sideways"

    lookback = min(len(series) - 1, 21)
    change_1m = float((price / series.iloc[-1 - lookback] - 1) * 100)

    return {
        "currentPrice": round(price, 2),
        "rsi": round(rsi, 2),
        "volatility": round(volatility, 2),
        "trend": trend,
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2) if ma50 is not None else None,
        "change1mPct": round(change_1m, 2),
        "observations": len(series),
    }
