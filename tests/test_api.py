import json

import pytest

from tests.fakes import FUNDAMENTALS, patch_data


@pytest.fixture
def client(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    import app as app_module
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_health(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "ok" and body["llmConfigured"] is False


@pytest.mark.parametrize("payload,field", [
    ({"ticker": "DROP TABLE;"}, "ticker"),
    ({"ticker": "RELIANCE", "age": 5}, "age"),
    ({"ticker": "RELIANCE", "portfolioValue": -10}, "portfolioValue"),
    ({"ticker": "RELIANCE", "riskAppetite": "YOLO"}, "riskAppetite"),
])
def test_bad_input_returns_400(client, payload, field):
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 400
    assert any(d["field"] == field for d in res.get_json()["details"])


def test_analyze_end_to_end(client, monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco profit rises"])
    res = client.post("/api/analyze", json={"ticker": "testco.ns", "portfolioValue": 100000})
    body = res.get_json()
    assert res.status_code == 200 and body["ticker"] == "TESTCO"
    trace = client.get(f"/api/runs/{body['meta']['runId']}/trace").get_json()
    assert len(trace["events"]) == len(body["trace"])


def test_unknown_symbol_returns_clear_error(client, monkeypatch):
    patch_data(monkeypatch, failing_sources=("marketstack", "alphavantage", "yfinance"))
    res = client.post("/api/analyze", json={"ticker": "NOSUCH"})
    assert res.status_code == 502 and "NOSUCH" in res.get_json()["error"]


def test_stream_sends_trace_then_result(client, monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["x"])
    res = client.post("/api/analyze/stream", json={"ticker": "TESTCO"})
    text = res.get_data(as_text=True)
    kinds = [line[7:] for line in text.splitlines() if line.startswith("event: ")]
    assert kinds[0] == "start" and kinds[-1] == "result" and kinds.count("trace") > 20
    result = json.loads(text.rsplit("data: ", 1)[1])
    assert result["recommendation"] in ("BUY", "HOLD", "SELL")


def test_trace_rejects_bad_ids(client):
    assert client.get("/api/runs/../../etc/trace").status_code == 404


def test_login_required_when_enabled(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", True)
    assert client.post("/api/analyze", json={"ticker": "X"}).status_code == 401
    assert client.post("/signup", json={"email": "a@b.co", "password": "secret1"}).status_code == 200
    assert client.post("/api/analyze", json={"ticker": "!!"}).status_code == 400  # now logged in


def test_passwords_are_salted_hashes(client):
    import app as app_module
    client.post("/signup", json={"email": "z@b.co", "password": "secret1"})
    with app_module.get_db() as db:
        stored = db.execute("SELECT pw FROM users WHERE email='z@b.co'").fetchone()["pw"]
    assert stored.startswith(("scrypt:", "pbkdf2:"))
