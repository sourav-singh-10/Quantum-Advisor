"""Watchlist, company search, daily briefs, intraday alerts and the brief schedule."""
import io
from datetime import datetime, timedelta

import pytest

from core.watch_store import MAX_WATCHLIST, WatchStore
from services import briefs
from tests.fakes import FakeLLM, price_series
from tools import market_snapshot, news_data, symbols
from tools.base import ToolError


def _today():
    return briefs.now_ist().date().isoformat()


def fake_market(monkeypatch, moves=None, missing=()):
    """yfinance stand-in: 250 rising closes; ``moves`` sets the last day's % change per symbol."""
    moves = moves or {}

    def year(symbol):
        if symbol in missing:
            raise ToolError("no rows")
        closes = price_series(250, start=100, drift=0.001, wobble=0.004)
        closes[-1] = closes[-2] * (1 + moves.get(symbol, 0.5) / 100)
        vols = [1000.0] * 249 + [3000.0]
        dates = [f"d{i}" for i in range(249)] + [_today()]
        return closes, vols, dates
    monkeypatch.setattr(market_snapshot, "_yf_year", year)
    from tools import market_data
    for src in market_data.SOURCES:
        monkeypatch.setitem(market_data._FETCHERS, src, lambda s: (_ for _ in ()).throw(ToolError("off")))


def fake_news(monkeypatch, titles_by_query):
    def fetch(query):
        for key, titles in titles_by_query.items():
            if key.lower() in query.lower():
                return [{"title": t, "source": "Test", "published": None, "link": "https://x.test"} for t in titles]
        raise ToolError("nothing")
    for src in news_data.SOURCES:
        monkeypatch.setitem(news_data._FETCHERS, src, fetch)


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr(briefs, "LLMClient", lambda: FakeLLM(available=False))


# ---------------------------------------------------------------- search
def test_search_finds_by_symbol_name_and_alias():
    assert symbols.search("zomato")[0]["symbol"] == "ETERNAL"
    assert symbols.search("tata")[0]["symbol"] == "TCS"
    assert symbols.search("airtel")[0]["symbol"] == "BHARTIARTL"
    assert symbols.search("hdfcb")[0]["symbol"] == "HDFCBANK"
    assert symbols.search("") == []


def test_suggest_falls_back_to_live_search(monkeypatch):
    monkeypatch.setattr(symbols, "live_search", lambda q: [{"symbol": "RAREMID", "name": "Rare Mid Ltd", "source": "live"}])
    out = symbols.suggest("raremid")
    assert out[-1]["symbol"] == "RAREMID" and out[-1]["source"] == "live"


# ---------------------------------------------------------------- tools
def test_snapshot_reports_day_move_range_and_volume(monkeypatch):
    fake_market(monkeypatch, moves={"TCS": -4.0})
    s = market_snapshot.snapshot("TCS")
    assert s["changePct"] == pytest.approx(-4.0, abs=0.01)
    assert s["rangeLabel"] == "52-week" and s["low52"] <= s["price"] <= s["high52"]
    assert s["volumeRatio"] == 3.0 and s["asOf"] == _today()


def test_snapshot_uses_the_new_symbol_after_a_rename(monkeypatch):
    fake_market(monkeypatch)
    assert market_snapshot.snapshot("ZOMATO")["ticker"] == "ETERNAL"


def test_company_news_keeps_relevant_and_marks_material(monkeypatch):
    from tools.news_watch import company_news
    fake_news(monkeypatch, {"Infosys": ["Infosys Q2 profit beats estimates - Mint",
                                        "Sensex ends flat as markets wait",
                                        "Infosys holds town hall for staff"]})
    out = company_news("INFY", "Infosys Limited")
    assert [n["title"] for n in out] == ["Infosys Q2 profit beats estimates", "Infosys holds town hall for staff"]
    assert out[0]["material"] and out[0]["tone"] == "Positive" and not out[1]["material"]


# ---------------------------------------------------------------- store
def test_watchlist_add_remove_and_limit(tmp_path):
    st = WatchStore(str(tmp_path / "w.db"))
    for i in range(MAX_WATCHLIST):
        assert st.add_watch("u", f"S{i}", None)
    assert not st.add_watch("u", "ONEMORE", None)
    assert st.add_watch("u", "S0", None)          # re-adding is fine
    st.remove_watch("u", "S0")
    assert len(st.watchlist("u")) == MAX_WATCHLIST - 1


def test_holdings_merge_repeated_rows(tmp_path):
    st = WatchStore(str(tmp_path / "w.db"))
    st.replace_holdings("u", [{"ticker": "TCS", "quantity": 10, "buy_price": 3000},
                              {"ticker": "TCS", "quantity": 10, "buy_price": 4000},
                              {"ticker": "ITC", "quantity": 0, "buy_price": 400}])
    (h,) = st.holdings("u")
    assert h["quantity"] == 20 and h["buy_price"] == 3500


def test_alerts_are_stored_once(tmp_path):
    st = WatchStore(str(tmp_path / "w.db"))
    assert st.add_alert("u", "TCS", "news", "k1", "title")
    assert not st.add_alert("u", "TCS", "news", "k1", "title")
    assert len(st.alerts("u")) == 1


# ---------------------------------------------------------------- briefs
def test_morning_brief_without_llm(monkeypatch, tmp_path, no_llm):
    fake_market(monkeypatch, moves={"INFY": 4.2, "ITC": -0.3})
    fake_news(monkeypatch, {"Infosys": ["Infosys wins large deal from European bank"]})
    st = WatchStore(str(tmp_path / "w.db"))
    st.add_watch("u", "INFY", "Infosys Limited")
    st.add_watch("u", "ITC", "ITC Limited")
    b = briefs.build_morning(st, "u")
    infy = next(i for i in b["items"] if i["ticker"] == "INFY")
    assert any("Up 4.2%" in f["text"] for f in infy["flags"])
    assert "INFY +4.2%" in b["summary"]["headline"] and b["summary"]["byLLM"] is False
    assert st.brief("u", "morning", _today())["runId"] == b["runId"]


def test_morning_brief_uses_the_llm_when_available(monkeypatch, tmp_path):
    fake_market(monkeypatch)
    fake_news(monkeypatch, {})
    llm = FakeLLM({("BriefAgent", "BriefSummary"): [{"headline": "Quiet open expected.",
                                                     "points": ["TCS: steady."], "actions": []}]})
    monkeypatch.setattr(briefs, "LLMClient", lambda: llm)
    st = WatchStore(str(tmp_path / "w.db"))
    st.add_watch("u", "TCS", "Tata Consultancy Services Limited")
    b = briefs.build_morning(st, "u")
    assert b["summary"]["headline"] == "Quiet open expected." and b["summary"]["byLLM"]
    assert "TCS" in llm.calls[0][2] and "RSI" in llm.calls[0][2]


def test_closing_brief_pnl_weights_and_suggestions(monkeypatch, tmp_path, no_llm):
    fake_market(monkeypatch, moves={"TCS": -5.0, "ITC": 1.0}, missing=("GONE",))
    fake_news(monkeypatch, {"Tata Consultancy": ["TCS shares plunge after weak quarterly results"]})
    st = WatchStore(str(tmp_path / "w.db"))
    st.replace_holdings("u", [{"ticker": "TCS", "quantity": 10, "buy_price": 100},
                              {"ticker": "ITC", "quantity": 1, "buy_price": 100},
                              {"ticker": "GONE", "quantity": 5, "buy_price": 10}])
    b = briefs.build_closing(st, "u")
    tcs = next(i for i in b["items"] if i["ticker"] == "TCS")
    assert tcs["dayPnL"] == pytest.approx(10 * (tcs["price"] - tcs["prevClose"]), abs=0.01)
    assert tcs["weight"] > 80
    assert b["totals"]["dayPnL"] < 0 and "down" in b["summary"]["headline"]
    text = " ".join(b["totals"]["suggestions"])
    assert "TCS is down 5.0% with negative news" in text and "Avoid adding more" in text
    assert next(i for i in b["items"] if i["ticker"] == "GONE")["error"]


def test_sweep_raises_each_alert_once(monkeypatch, tmp_path):
    fake_market(monkeypatch, moves={"INFY": -3.5})
    fake_news(monkeypatch, {"Infosys": ["Infosys shares slump after SEBI probe", "Infosys holds AGM"]})
    st = WatchStore(str(tmp_path / "w.db"))
    st.add_watch("u", "INFY", "Infosys Limited")
    assert briefs.sweep(st) == 2          # one material headline + one big move
    assert briefs.sweep(st) == 0
    kinds = {a["kind"]: a for a in st.alerts("u")}
    assert kinds["price"]["tone"] == "down" and "down 3.5%" in kinds["price"]["title"]


def _at(day_offset_to_weekday, hh, mm):
    base = datetime(2026, 10, 19, tzinfo=briefs.IST)        # a Monday
    return base + timedelta(days=day_offset_to_weekday, hours=hh, minutes=mm)


def test_schedule_runs_each_job_at_its_time_once(monkeypatch, tmp_path, no_llm):
    fake_market(monkeypatch)
    fake_news(monkeypatch, {})
    st = WatchStore(str(tmp_path / "w.db"))
    st.add_watch("u", "TCS", "Tata Consultancy Services Limited")
    st.replace_holdings("u", [{"ticker": "TCS", "quantity": 1, "buy_price": 90}])
    sent = []
    notify = lambda u, b: sent.append(b["kind"])
    assert briefs.run_due(st, _at(0, 8, 29), notify) == []
    assert briefs.run_due(st, _at(0, 8, 31), notify) == ["morning"]
    assert briefs.run_due(st, _at(0, 8, 40), notify) == []
    assert briefs.run_due(st, _at(0, 10, 0), notify) == ["sweep"]
    assert briefs.run_due(st, _at(0, 10, 10), notify) == []
    assert briefs.run_due(st, _at(0, 15, 16), notify) == ["closing", "sweep"]
    assert briefs.run_due(st, _at(5, 9, 0), notify) == []      # Saturday
    assert sent == ["morning", "closing"]


def test_user_gets_missed_briefs_when_they_open_the_page(tmp_path):
    st = WatchStore(str(tmp_path / "w.db"))
    st.add_watch("u", "TCS", None)
    assert briefs.due_for_user(st, "u", _at(0, 8, 0)) == []
    assert briefs.due_for_user(st, "u", _at(0, 16, 0)) == ["morning"]   # no holdings, no closing


# ---------------------------------------------------------------- API
@pytest.fixture
def client(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    import app as app_module
    app_module.init_db()
    app_module._refresh_at.clear()
    return app_module.app.test_client()


def test_api_watchlist_and_brief(client, monkeypatch, no_llm):
    fake_market(monkeypatch, missing=("NOPE", "INFOSYS"))
    fake_news(monkeypatch, {})
    assert client.post("/api/watchlist", json={"ticker": "Infosys"}).get_json()["added"] == "INFY"
    client.delete("/api/watchlist/INFY")
    assert client.post("/api/watchlist", json={"ticker": "bad symbol!"}).status_code == 400
    assert client.post("/api/watchlist", json={"ticker": "NOPE"}).status_code == 400
    body = client.post("/api/watchlist", json={"ticker": "zomato"}).get_json()
    assert body["added"] == "ETERNAL" and body["items"][0]["name"].startswith("Eternal")
    assert client.get("/api/symbols?q=infos").get_json()["results"][0]["symbol"] == "INFY"
    res = client.post("/api/briefs/morning/refresh")
    assert res.status_code == 200 and res.get_json()["morning"]["items"][0]["ticker"] == "ETERNAL"
    assert client.post("/api/briefs/morning/refresh").status_code == 429
    assert client.post("/api/briefs/closing/refresh").status_code == 400     # no holdings yet
    assert client.delete("/api/watchlist/ETERNAL").get_json()["items"] == []


def test_api_holdings_upload(client):
    csv = b"ticker,quantity,buy_price\nTCS.NS,5,3000\nINFY,10,1500\n"
    body = client.post("/api/holdings", data={"file": (io.BytesIO(csv), "h.csv")},
                       content_type="multipart/form-data").get_json()
    assert body["saved"] == 2 and {h["ticker"] for h in body["items"]} == {"TCS", "INFY"}


def test_cron_needs_the_secret(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "CRON_SECRET", "")
    assert client.get("/api/cron/tick?key=x").status_code == 403
    monkeypatch.setattr(config, "CRON_SECRET", "s3cret")
    assert client.get("/api/cron/tick?key=wrong").status_code == 403
    assert client.post("/api/cron/tick", headers={"X-Cron-Key": "s3cret"}).status_code == 202
