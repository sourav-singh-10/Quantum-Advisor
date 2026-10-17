"""Scorecard: reads the analysts' numbers, skips what is missing, flags what matters."""
from tools.scorecard import entry_point, red_flags, scorecard


def test_scores_come_from_the_analysis_and_missing_data_is_skipped():
    d = {"trend": "Uptrend", "change1mPct": 8.0, "macdState": "Bullish", "pe": 15.9, "roe": 25,
         "profitMargin": 25, "healthScore": 60, "financialHealth": "Stable", "fundamentalsAvailable": True,
         "newsAvailable": False, "rsi": 55, "bbPercentB": 0.5, "toSupportPct": -8}
    card = scorecard(d)
    by = {s["name"]: s for s in card["scores"]}
    assert by["Momentum"]["score"] == 10 and by["Valuation"]["score"] == 7
    assert by["Profitability"]["score"] == 10 and by["Financial health"]["score"] == 6
    assert "News" not in by
    assert card["entry"]["verdict"] == "Fair" and card["redFlags"] == []


def test_entry_point_and_red_flags():
    assert entry_point({"rsi": 78})["verdict"] == "Stretched"
    assert entry_point({"rsi": 50, "bbPercentB": 0.1})["verdict"] == "Good"
    flags = red_flags({"rsi": 80, "volatility": 3.1, "de": 2.4, "pe": -5, "maxDrawdownPct": -35,
                       "sentimentScore": -1, "materialHeadlines": ["x"], "documentConflicts": ["y"]})
    assert len(flags) == 7 and flags[0].startswith("Deeply overbought")


def test_loss_maker_scores_low_on_valuation_and_one_figure_profitability_is_rescaled():
    by = {s["name"]: s["score"] for s in scorecard({"pe": -3, "roe": 12.5})["scores"]}
    assert by["Valuation"] == 1 and by["Profitability"] == 5
