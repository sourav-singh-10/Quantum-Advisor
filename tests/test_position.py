from tools.position import position_size, price_targets


def test_no_position_unless_buy():
    assert position_size(100000, 500, "HOLD", 80)["units"] == 0
    assert position_size(100000, 500, "SELL", 80)["units"] == 0


def test_position_respects_profile_limit():
    buy = position_size(100000, 500, "BUY", 50, max_position_pct=4)
    assert buy["positionPct"] == 4 and buy["units"] == 8 and buy["amount"] == 4000


def test_targets_scale_with_volatility():
    calm, wild = price_targets(100, 0.8, "BUY"), price_targets(100, 3, "BUY")
    assert wild["targetPrice1"] > calm["targetPrice1"] and wild["stopLoss"] < calm["stopLoss"]


def test_sell_targets_point_down():
    t = price_targets(100, 2, "SELL")
    assert t["targetPrice1"] < 100 < t["stopLoss"]
