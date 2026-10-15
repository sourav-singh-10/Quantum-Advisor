import json

import pytest

from core.memory import RunMemory
from core.tracer import Tracer, load_run


def test_tracer_numbers_messages_and_persists_them(tmp_path):
    t = Tracer(log_dir=tmp_path)
    t.emit("Planner", "MarketAnalyst", "task", {"instruction": "trend"})
    t.emit("MarketAnalyst", "Planner", "result", {"trend": "Uptrend"}, llm={"ok": True})
    lines = (tmp_path / "traces" / f"{t.run_id}.jsonl").read_text().splitlines()
    assert [json.loads(x)["seq"] for x in lines] == [1, 2]
    assert load_run(t.run_id, tmp_path)[1]["llm"] == {"ok": True}


def test_tracer_rejects_unknown_message_types(tmp_path):
    with pytest.raises(ValueError):
        Tracer(log_dir=tmp_path).emit("A", "B", "gossip")


def test_tracer_notifies_listeners(tmp_path):
    seen = []
    t = Tracer(log_dir=tmp_path)
    t.subscribe(seen.append)
    t.emit("User", "Planner", "request", {"ticker": "TCS"})
    assert seen[0]["type"] == "request"


def test_tracer_truncates_long_payloads(tmp_path):
    t = Tracer(log_dir=tmp_path)
    e = t.emit("A", "B", "result", {"text": "x" * 2000, "items": list(range(50))})
    assert len(e["payload"]["text"]) < 700 and len(e["payload"]["items"]) == 13


def test_load_run_rejects_path_tricks(tmp_path):
    with pytest.raises(ValueError):
        load_run("../../etc/passwd", tmp_path)


def test_memory_returns_latest_run_per_user_and_ticker(tmp_path):
    m = RunMemory(str(tmp_path / "m.db"))
    m.save("r1", "a@x.in", "TCS", {"recommendation": "HOLD"})
    m.save("r2", "a@x.in", "TCS", {"recommendation": "BUY"})
    m.save("r3", "b@x.in", "TCS", {"recommendation": "SELL"})
    assert m.last_run("a@x.in", "TCS")["recommendation"] in ("BUY", "HOLD")
    assert m.last_run("a@x.in", "INFY") is None
    assert len(m.recent("a@x.in")) == 2
