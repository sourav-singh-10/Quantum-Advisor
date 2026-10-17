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
    # The moving-average cross alone lags: a stock that has rebounded 15% above both
    # averages would still read "Downtrend". So the price has to agree with the cross,
    # and a decisive move through both averages (3%+) counts on its own.
    high, low = max(ma20, reference), min(ma20, reference)
    if (ma20 > reference * 1.005 and price > reference) or price > high * 1.03:
        trend = "Uptrend"
    elif (ma20 < reference * 0.995 and price < reference) or price < low * 0.97:
        trend = "Downtrend"
    else:
        trend = "Sideways"

    # Drawdowns: the worst peak-to-trough fall in the window, and how far the price is
    # below its highest close right now.
    running_peak = series.cummax()
    max_drawdown = float(((series / running_peak) - 1).min() * 100)
    from_high = float((price / float(series.max()) - 1) * 100)

    lookback = min(len(series) - 1, 21)
    change_1m = float((price / series.iloc[-1 - lookback] - 1) * 100)

    out = {
        "currentPrice": round(price, 2),
        "rsi": round(rsi, 2),
        "volatility": round(volatility, 2),
        "trend": trend,
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2) if ma50 is not None else None,
        "change1mPct": round(change_1m, 2),
        "maxDrawdownPct": round(max_drawdown, 2),
        "belowHighPct": round(from_high, 2),
        "observations": len(series),
    }
    out.update(extra_indicators(series))
    return out


def extra_indicators(series: pd.Series) -> dict:
    """MACD, Bollinger bands, momentum and nearby support/resistance from closing prices."""
    out: dict = {}
    price = float(series.iloc[-1])

    # MACD (12, 26, 9): the gap between a fast and a slow average, and its own signal line.
    if len(series) >= 35:
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        prev_hist = float(hist.iloc[-2])
        cur_hist = float(hist.iloc[-1])
        if prev_hist <= 0 < cur_hist:
            cross = "Bullish crossover"
        elif prev_hist >= 0 > cur_hist:
            cross = "Bearish crossover"
        else:
            cross = "Bullish" if cur_hist > 0 else "Bearish"
        out.update({"macd": round(float(macd.iloc[-1]), 2), "macdSignal": round(float(signal.iloc[-1]), 2),
                    "macdHist": round(cur_hist, 2), "macdState": cross})

    # Bollinger bands (20, 2): where the price sits inside its normal range.
    if len(series) >= 20:
        mid = series.rolling(20).mean().iloc[-1]
        sd = series.rolling(20).std().iloc[-1]
        upper, lower = float(mid + 2 * sd), float(mid - 2 * sd)
        width = upper - lower
        pct_b = (price - lower) / width if width else 0.5
        state = ("Above upper band" if pct_b > 1 else "Near upper band" if pct_b > 0.8
                 else "Below lower band" if pct_b < 0 else "Near lower band" if pct_b < 0.2
                 else "Inside the bands")
        out.update({"bbUpper": round(upper, 2), "bbLower": round(lower, 2),
                    "bbPercentB": round(pct_b, 2), "bbWidthPct": round(width / float(mid) * 100, 2),
                    "bbState": state})

    # Momentum: rate of change over three months, when the window allows.
    if len(series) > 63:
        out["change3mPct"] = round((price / float(series.iloc[-64]) - 1) * 100, 2)

    # Support and resistance: the lowest and highest closes of the last 60 sessions.
    recent = series.iloc[-60:]
    support, resistance = float(recent.min()), float(recent.max())
    out.update({"support": round(support, 2), "resistance": round(resistance, 2),
                "toSupportPct": round((support / price - 1) * 100, 2),
                "toResistancePct": round((resistance / price - 1) * 100, 2)})
    return out


def long_view(closes: list[float]) -> dict:
    """A one-year look for follow-up questions: return, range, worst fall and the 200-day average."""
    if not closes or len(closes) < 60:
        raise ToolError("need at least 60 closes for a long view")
    s = pd.Series(closes[-250:], dtype="float64")
    price = float(s.iloc[-1])
    peak = s.cummax()
    out = {"sessions": len(s), "change1yPct": round((price / float(s.iloc[0]) - 1) * 100, 2),
           "high": round(float(s.max()), 2), "low": round(float(s.min()), 2),
           "fromHighPct": round((price / float(s.max()) - 1) * 100, 2),
           "fromLowPct": round((price / float(s.min()) - 1) * 100, 2),
           "maxDrawdownPct": round(float(((s / peak) - 1).min() * 100), 2)}
    if len(s) >= 200:
        ma200 = float(s.rolling(200).mean().iloc[-1])
        out.update({"ma200": round(ma200, 2), "above200dma": price > ma200})
    return out
