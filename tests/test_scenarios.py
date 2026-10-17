"""Simulated failures for the evaluation: gated by EVAL_FAULTS, visible in the trace, adapted to."""
import pytest

from tests.fakes import FUNDAMENTALS, patch_data


@pytest.fixture
def client(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    import app as app_module
    app_module.init_db()
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["Testco profit rises"])
    return app_module.app.test_client()


BODY = {"ticker": "TESTCO", "portfolioValue": 100000}


def test_fault_header_is_ignored_unless_the_server_allows_it(client):
    out = client.post("/api/analyze", json=BODY, headers={"X-Eval-Fault": "agent:NewsAnalyst"}).get_json()
    assert out["meta"]["replans"] == 0
    assert not any("Evaluation mode" in str(e.get("payload")) for e in out["trace"])


def test_failed_analyst_is_replanned_and_the_trace_says_it_was_simulated(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "EVAL_FAULTS", True)
    out = client.post("/api/analyze", json=BODY, headers={"X-Eval-Fault": "agent:NewsAnalyst"}).get_json()
    assert out["meta"]["replans"] == 1 and out["newsSentiment"] != "Not analysed"
    notes = [e for e in out["trace"] if e["type"] == "decision" and "Evaluation mode" in str(e["payload"])]
    assert notes and "not real outages" in notes[0]["payload"]["note"]
    assert any(e["type"] == "error" and "simulated" in e["payload"]["error"] for e in out["trace"])


def test_price_source_outage_is_worked_around(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "EVAL_FAULTS", True)
    out = client.post("/api/analyze", json=BODY,
                      headers={"X-Eval-Fault": "tool:get_price_history:yfinance"}).get_json()
    failed = [e for e in out["trace"] if e["type"] == "tool_result" and not e["payload"].get("ok", True)]
    assert failed and "simulated outage" in failed[0]["payload"]["error"]
    assert out["priceSource"] != "yfinance" and out["recommendation"] in ("BUY", "HOLD", "SELL")


def test_malformed_fault_names_are_dropped(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "EVAL_FAULTS", True)
    out = client.post("/api/analyze", json=BODY, headers={"X-Eval-Fault": "agent:x; rm -rf /"}).get_json()
    assert out["meta"]["replans"] == 0
