"""Today screen, saved-holdings review, user price alerts, Telegram linking and the track record."""
import io

import pytest

from core.watch_store import WatchStore
from services import briefs, telegram
from services.track_record import judge, outcome, track_record
from tests.fakes import FakeLLM
from tests.test_watchlist import fake_market, fake_news


@pytest.fixture
def client(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    import app as app_module
    app_module.init_db()
    monkeypatch.setattr(briefs, "LLMClient", lambda: FakeLLM(available=False))
    return app_module.app.test_client()


# ---------------------------------------------------------------- track record
def test_calls_are_judged_four_weeks_later():
    assert judge("BUY", 3.0) == "right" and judge("BUY", -1) == "wrong"
    assert judge("SELL", -2) == "right" and judge("HOLD", 4.9) == "right" and judge("HOLD", -7) == "wrong"
    dates = [f"2026-08-{d:02d}" for d in range(1, 31)]
    closes = [100.0 + i for i in range(30)]
    run = {"run_id": "r1", "ticker": "X", "created_at": "2026-08-03T04:00:00+00:00",
           "recommendation": "BUY", "price": 102.0}
    row = outcome(run, closes, dates)
    assert row["after1w"] == pytest.approx((107 / 102 - 1) * 100, abs=0.01)
    assert row["after4w"] == pytest.approx((122 / 102 - 1) * 100, abs=0.01) and row["verdict"] == "right"
    recent = {**run, "created_at": "2026-08-25T04:00:00+00:00"}
    assert outcome(recent, closes, dates)["verdict"] == "too early"


def test_track_record_summary_counts_only_judged_calls():
    dates = [f"2026-07-{d:02d}" for d in range(1, 31)] + [f"2026-08-{d:02d}" for d in range(1, 11)]
    closes = [100.0] * 40
    runs = [{"run_id": f"r{i}", "ticker": "FLAT", "created_at": "2026-07-02T04:00:00+00:00",
             "recommendation": rec, "price": 100.0} for i, rec in enumerate(["HOLD", "BUY"])]
    out = track_record(runs, lambda t: (closes, [], dates))
    s = out["summary"]
    assert s["judged"] == 2 and s["right"] == 1 and s["byRecommendation"]["HOLD"]["right"] == 1


# ---------------------------------------------------------------- price alerts
def test_price_alert_validation_and_trigger(client, monkeypatch, tmp_path):
    fake_market(monkeypatch, moves={"INFY": -1.0})
    fake_news(monkeypatch, {})
    assert client.post("/api/price-alerts", json={"ticker": "INFY", "direction": "sideways", "price": 1}).status_code == 400
    now = client.get("/api/today/live").get_json()        # nothing saved yet: empty but fine
    assert now["holdings"] is None
    from tools.market_snapshot import snapshot
    price = snapshot("INFY")["price"]
    bad = client.post("/api/price-alerts", json={"ticker": "INFY", "direction": "below", "price": price + 5})
    assert bad.status_code == 400 and "Pick a level below" in bad.get_json()["error"]
    ok = client.post("/api/price-alerts", json={"ticker": "INFY", "direction": "below", "price": price - 5})
    assert ok.status_code == 200 and len(ok.get_json()["items"]) == 1

    store = WatchStore()
    assert briefs.sweep(store) == 0                      # not reached yet
    fake_market(monkeypatch, moves={"INFY": -9.0})
    from tools.base import clear_cache
    clear_cache()
    told = []
    assert briefs.sweep(store, on_alert=lambda u, a: told.append(a)) >= 1
    target = [a for a in told if a["kind"] == "target"]
    assert target and "fallen to" in target[0]["title"]
    assert client.get("/api/price-alerts").get_json()["items"][0]["triggered_at"]
    assert briefs.sweep(store) == 0                      # each level fires once


# ---------------------------------------------------------------- holdings
def test_upload_can_save_holdings_and_review_them_again(client, monkeypatch):
    from tools import portfolio_analyzer
    monkeypatch.setattr(portfolio_analyzer, "live_quote", lambda t: {
        "price": 110.0, "volatility": 1.2, "source": "yfinance", "trend": "Sideways", "rsi": 50,
        "pe": 20, "sector": "IT", "history": [100.0, 110.0]})
    csv = b"ticker,quantity,buy_price\nTCS,5,100\nINFY,10,100\n"
    body = client.post("/upload_portfolio", data={"file": (io.BytesIO(csv), "h.csv"), "save": "1"},
                       content_type="multipart/form-data").get_json()
    assert body["saved"] == 2
    again = client.post("/api/holdings/review").get_json()
    assert {s["ticker"] for s in again["stocks"]} == {"TCS", "INFY"} and again["review"]


# ---------------------------------------------------------------- Today
def test_today_summary_and_live_numbers(client, monkeypatch):
    fake_market(monkeypatch, moves={"TCS": 2.0, "ITC": -1.0})
    fake_news(monkeypatch, {})
    client.put("/api/profile", json={"name": "Sourav", "age": 30,
                                     "goals": [{"title": "College", "amount": 1000000, "year": 2032}]})
    client.post("/api/watchlist", json={"ticker": "ITC"})
    client.post("/upload_portfolio", data={"file": (io.BytesIO(b"ticker,quantity,buy_price\nTCS,10,90\n"), "h.csv"),
                                           "save": "1"}, content_type="multipart/form-data")
    t = client.get("/api/today").get_json()
    assert t["name"] == "Sourav" and t["greeting"].startswith("Good") and t["goals"][0]["yearsLeft"] >= 5
    assert t["watchCount"] == 1 and t["holdingsCount"] == 1 and "Market" in t["marketStatus"]
    live = client.get("/api/today/live").get_json()
    assert live["holdings"]["count"] == 1 and live["holdings"]["dayPnL"] > 0
    assert live["watch"][0]["ticker"] == "ITC"


# ---------------------------------------------------------------- Telegram
def test_telegram_links_a_chat_from_the_start_code(client, monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(config, "TELEGRAM_BOT_NAME", "qa_bot")
    sent = []

    def fake_call(method, **params):
        if method == "getUpdates":
            return {"ok": True, "result": [{"update_id": 7, "message": {"text": f"/start {code}", "chat": {"id": 42}}},
                                           {"update_id": 8, "message": {"text": "/start oldcode", "chat": {"id": 43}}}]}
        sent.append((params.get("chat_id"), params.get("text")))
        return {"ok": True}
    monkeypatch.setattr(telegram, "_call", fake_call)
    link = client.post("/api/telegram/link").get_json()
    code = link["code"]
    assert link["url"] == f"https://t.me/qa_bot?start={code}"
    assert client.get("/api/telegram").get_json() == {"available": True, "linked": True}
    assert sent[0][0] == "42" and "Connected" in sent[0][1] and "expired" in sent[1][1]
    store = WatchStore()
    assert store.last_job("telegram_offset") == "9"
    import app as app_module
    app_module._on_alert("anonymous", {"ticker": "TCS", "title": "x", "link": ""})
    assert sent[-1] == ("42", "TCS: x")
    assert client.delete("/api/telegram").get_json()["linked"] is False
