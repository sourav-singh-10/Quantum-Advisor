"""The call is worded for the investor's position, and unsuitability never turns into SELL."""
from agents.strategy_agent import baseline
from tools.actions import action_for


def test_labels_depend_on_whether_the_investor_holds_the_stock():
    assert action_for("SELL", False)["label"] == "Avoid" and action_for("SELL", True)["label"] == "Sell"
    assert action_for("HOLD", False)["label"] == "Wait" and action_for("HOLD", True)["label"] == "Keep"
    assert action_for("BUY", True)["label"] == "Add more"
    risky = action_for("HOLD", False, suitability_gap=25)
    assert risky["tooRiskyForYou"] and "riskier than your profile" in risky["text"]


def test_baseline_keeps_stock_view_and_fit_apart():
    assert baseline(15, 0, "Uptrend") == "BUY"
    assert baseline(15, 25, "Uptrend") == "HOLD"        # good stock, wrong investor: not SELL
    assert baseline(15, 0, "Downtrend") == "HOLD"
    assert baseline(55, 0, "Uptrend") == "SELL"         # only a weak stock is a SELL


def test_holding_comes_from_saved_holdings_unless_the_client_says(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    import app as app_module
    from tests.fakes import FUNDAMENTALS, patch_data
    app_module.init_db()
    client = app_module.app.test_client()
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco profit rises"])
    first = client.post("/api/analyze", json={"ticker": "TESTCO", "portfolioValue": 100000}).get_json()
    assert first["holding"] is False and first["action"]["label"] in ("Buy", "Wait", "Avoid")
    told = client.post("/api/analyze", json={"ticker": "TESTCO", "portfolioValue": 100000,
                                             "holding": True}).get_json()
    assert told["holding"] is True and told["action"]["label"] in ("Add more", "Keep", "Sell")
    assert set(told["meta"]["models"]) == set()          # no LLM in tests: no model answered
