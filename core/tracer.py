"""Message-level execution trace.

Every hand-off between agents, every tool call and every LLM decision becomes one JSON line:
    {run_id, seq, ts, from, to, type, round, payload, llm}
Lines go to logs/traces/<run_id>.jsonl (one file per run) and to logs/agent_trace.jsonl
(all runs). Listeners (the streaming endpoint) receive each event as it happens.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import config

MESSAGE_TYPES = {
    "request", "plan", "task", "tool_call", "tool_result", "result", "error",
    "replan", "assessment", "draft", "critique", "arbitration", "decision",
    "final", "memory", "challenge", "reply", "reconciliation", "followup", "answer",
}


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("r_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]


def _short(value, limit=600):
    """Keep trace lines readable: long strings and lists are truncated, never dropped silently."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"... [+{len(value) - limit} chars]"
    if isinstance(value, list):
        items = [_short(v, limit) for v in value[:12]]
        if len(value) > 12:
            items.append(f"... [+{len(value) - 12} items]")
        return items
    if isinstance(value, dict):
        return {k: _short(v, limit) for k, v in value.items()}
    return value


class Tracer:
    def __init__(self, run_id: Optional[str] = None, log_dir: Optional[Path] = None,
                 persist: bool = True):
        self.run_id = run_id or new_run_id()
        self.events: list[dict] = []
        self._seq = 0
        self._lock = threading.Lock()
        self._listeners: list[Callable[[dict], None]] = []
        self.persist = persist
        self.log_dir = Path(log_dir or config.LOG_DIR)
        if persist:
            (self.log_dir / "traces").mkdir(parents=True, exist_ok=True)

    @property
    def run_file(self) -> Path:
        return self.log_dir / "traces" / f"{self.run_id}.jsonl"

    def subscribe(self, fn: Callable[[dict], None]) -> None:
        self._listeners.append(fn)

    def emit(self, sender: str, receiver: str, type_: str, payload: Optional[dict] = None,
             round_: Optional[int] = None, llm: Optional[dict] = None) -> dict:
        if type_ not in MESSAGE_TYPES:
            raise ValueError(f"unknown message type {type_}")
        with self._lock:
            self._seq += 1
            event = {
                "run_id": self.run_id,
                "seq": self._seq,
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "from": sender,
                "to": receiver,
                "type": type_,
                "round": round_,
                "payload": _short(payload or {}),
            }
            if llm:
                event["llm"] = llm
            self.events.append(event)
            if self.persist:
                line = json.dumps(event, default=str, ensure_ascii=False) + "\n"
                with self.run_file.open("a", encoding="utf-8") as fh:
                    fh.write(line)
                with (self.log_dir / "agent_trace.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(line)
        for fn in list(self._listeners):
            try:
                fn(event)
            except Exception:
                pass
        return event


def load_run(run_id: str, log_dir: Optional[Path] = None) -> list[dict]:
    if not run_id.replace("_", "").isalnum():
        raise ValueError("invalid run id")
    path = Path(log_dir or config.LOG_DIR) / "traces" / f"{run_id}.jsonl"
    if not path.exists():
        raise FileNotFoundError(run_id)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
