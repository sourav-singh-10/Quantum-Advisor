from tools.fundamentals_data import score_fundamentals


def test_strong_company_scores_high():
    out = score_fundamentals({"pe": 18, "roe": 22, "de": 0.2, "profitMargin": 15})
    assert out["financialHealth"] == "Strong" and out["missing"] == []


def test_leveraged_loss_maker_scores_weak():
    out = score_fundamentals({"pe": -5, "roe": 3, "de": 3.5, "profitMargin": -4})
    assert out["financialHealth"] == "Weak"


def test_missing_metrics_are_listed_not_guessed():
    out = score_fundamentals({"pe": None, "roe": 20, "de": 3, "profitMargin": 5})
    assert "PE" in out["missing"] and any("debt" in n for n in out["notes"])
