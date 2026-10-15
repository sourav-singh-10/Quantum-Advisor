"""Long-term memory: a short summary of every finished run, per user and ticker.

The Planner reads the previous run for the same ticker so it can notice what changed
("trend flipped since your last analysis") and the Report agent can mention it.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import config


class RunMemory:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH
        with self._conn() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                       run_id TEXT PRIMARY KEY,
                       user_key TEXT NOT NULL,
                       ticker TEXT NOT NULL,
                       created_at TEXT NOT NULL,
                       summary TEXT NOT NULL)"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS runs_user_ticker ON runs(user_key, ticker)")

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def last_run(self, user_key: str, ticker: str) -> Optional[dict]:
        with self._conn() as db:
            row = db.execute(
                "SELECT run_id, created_at, summary FROM runs WHERE user_key=? AND ticker=? "
                "ORDER BY created_at DESC LIMIT 1", (user_key, ticker)).fetchone()
        if not row:
            return None
        return {"run_id": row[0], "created_at": row[1], **json.loads(row[2])}

    def save(self, run_id: str, user_key: str, ticker: str, summary: dict) -> None:
        with self._conn() as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)",
                       (run_id, user_key, ticker,
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        json.dumps(summary, default=str)))

    def recent(self, user_key: str, limit: int = 10) -> list[dict]:
        with self._conn() as db:
            rows = db.execute(
                "SELECT run_id, ticker, created_at, summary FROM runs WHERE user_key=? "
                "ORDER BY created_at DESC LIMIT ?", (user_key, limit)).fetchall()
        return [{"run_id": r[0], "ticker": r[1], "created_at": r[2], **json.loads(r[3])}
                for r in rows]
