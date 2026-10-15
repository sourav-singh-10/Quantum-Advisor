"""Price targets and position sizing."""
from __future__ import annotations


def price_targets(price: float, volatility_pct: float, recommendation: str) -> dict:
    # Scale targets by volatility: a 2% daily mover gets wider bands than a 0.8% one.
    band = max(0.04, min(0.25, volatility_pct / 100 * 5))
    if recommendation == "SELL":
        return {"targetPrice1": round(price * (1 - band), 2),
                "targetPrice2": round(price * (1 - 2 * band), 2),
                "stopLoss": round(price * (1 + band), 2)}
    return {"targetPrice1": round(price * (1 + band), 2),
            "targetPrice2": round(price * (1 + 2 * band), 2),
            "stopLoss": round(price * (1 - band), 2)}


def position_size(portfolio_value: float, price: float, recommendation: str,
                  capacity: int, max_position_pct: float | None = None) -> dict:
    if recommendation != "BUY" or price <= 0:
        return {"positionPct": 0.0, "units": 0, "amount": 0.0}
    pct = 2 + capacity / 100 * 6            # 2% .. 8% of the portfolio
    if max_position_pct is not None:
        pct = min(pct, max_position_pct)
    amount = portfolio_value * pct / 100
    units = int(amount // price)
    return {"positionPct": round(pct, 1), "units": units, "amount": round(units * price, 2)}
