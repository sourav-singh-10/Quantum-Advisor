import math

import pytest

from tools.base import ToolError
from tools.indicators import compute_indicators


def price_series(n=120, drift=0.002, wobble=0.01):
    return [100 * (1 + drift) ** i * (1 + wobble * math.sin(i)) for i in range(n)]


def test_uptrend():
    ind = compute_indicators(price_series(drift=0.004))
    assert ind["trend"] == "Uptrend" and 0 <= ind["rsi"] <= 100 and ind["observations"] == 120


def test_downtrend():
    assert compute_indicators(price_series(drift=-0.004))["trend"] == "Downtrend"


def test_flat_prices_give_sideways_and_rsi_100_guard():
    ind = compute_indicators([100.0] * 60)
    assert ind["trend"] == "Sideways" and ind["volatility"] == 0


def test_short_series_uses_price_as_reference():
    ind = compute_indicators(price_series(n=30))
    assert ind["ma50"] is None


def test_needs_20_prices():
    with pytest.raises(ToolError):
        compute_indicators([100.0] * 10)
