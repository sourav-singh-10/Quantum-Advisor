"""Per-user watchlist, saved holdings, daily briefs and alerts (SQLite)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from core import db as dbm

MAX_WATCHLIST = 25
MAX_HOLDINGS = 40
MAX_PRICE_ALERTS = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class WatchStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path          # None: DATABASE_URL if set, else the local DB_PATH file
        dbm.ensure_schema("watch", self.db_path, lambda db: db.executescript("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    user_key TEXT NOT NULL, ticker TEXT NOT NULL, name TEXT,
                    added_at TEXT NOT NULL, PRIMARY KEY (user_key, ticker));
                CREATE TABLE IF NOT EXISTS holdings (
                    user_key TEXT NOT NULL, ticker TEXT NOT NULL, quantity REAL NOT NULL,
                    buy_price REAL NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_key, ticker));
                CREATE TABLE IF NOT EXISTS briefs (
                    user_key TEXT NOT NULL, kind TEXT NOT NULL, day TEXT NOT NULL,
                    created_at TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY (user_key, kind, day));
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT NOT NULL,
                    ticker TEXT NOT NULL, kind TEXT NOT NULL, dedupe TEXT NOT NULL,
                    title TEXT NOT NULL, detail TEXT, tone TEXT, link TEXT,
                    created_at TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (user_key, dedupe));
                CREATE INDEX IF NOT EXISTS alerts_user ON alerts(user_key, created_at);
                CREATE TABLE IF NOT EXISTS notify_settings (
                    user_key TEXT PRIMARY KEY, email_briefs INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS job_runs (
                    job TEXT PRIMARY KEY, last_run TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS price_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT NOT NULL,
                    ticker TEXT NOT NULL, direction TEXT NOT NULL, price REAL NOT NULL,
                    created_at TEXT NOT NULL, triggered_at TEXT, triggered_price REAL);
                CREATE TABLE IF NOT EXISTS telegram_links (
                    user_key TEXT PRIMARY KEY, chat_id TEXT NOT NULL, linked_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS telegram_codes (
                    code TEXT PRIMARY KEY, user_key TEXT NOT NULL, created_at TEXT NOT NULL);
            """))

    def _conn(self):
        return dbm.connect(self.db_path)

    # ---------------------------------------------------------------- watchlist
    def watchlist(self, user: str) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT ticker, name, added_at FROM watchlist WHERE user_key=? "
                              "ORDER BY added_at", (user,)).fetchall()
        return [dict(r) for r in rows]

    def add_watch(self, user: str, ticker: str, name: Optional[str]) -> bool:
        """False when the list is already full."""
        with self._conn() as db:
            n = db.execute("SELECT COUNT(*) FROM watchlist WHERE user_key=?", (user,)).fetchone()[0]
            exists = db.execute("SELECT 1 FROM watchlist WHERE user_key=? AND ticker=?",
                                (user, ticker)).fetchone()
            if not exists and n >= MAX_WATCHLIST:
                return False
            db.execute("INSERT OR IGNORE INTO watchlist VALUES (?,?,?,?)", (user, ticker, name, _now()))
        return True

    def remove_watch(self, user: str, ticker: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM watchlist WHERE user_key=? AND ticker=?", (user, ticker))

    # ---------------------------------------------------------------- holdings
    def holdings(self, user: str) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT ticker, quantity, buy_price, updated_at FROM holdings "
                              "WHERE user_key=? ORDER BY ticker", (user,)).fetchall()
        return [dict(r) for r in rows]

    def replace_holdings(self, user: str, rows: list[dict]) -> int:
        """Save the uploaded holdings, merging repeated tickers (weighted buy price)."""
        merged: dict[str, dict] = {}
        for r in rows:
            t, q, p = r["ticker"], float(r["quantity"]), float(r["buy_price"])
            if q <= 0:
                continue
            m = merged.setdefault(t, {"quantity": 0.0, "cost": 0.0})
            m["quantity"] += q
            m["cost"] += q * p
        items = list(merged.items())[:MAX_HOLDINGS]
        with self._conn() as db:
            db.execute("DELETE FROM holdings WHERE user_key=?", (user,))
            db.executemany("INSERT INTO holdings VALUES (?,?,?,?,?)",
                           [(user, t, m["quantity"], round(m["cost"] / m["quantity"], 4), _now())
                            for t, m in items])
        return len(items)

    def clear_holdings(self, user: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM holdings WHERE user_key=?", (user,))

    # ---------------------------------------------------------------- users with something to watch
    def active_users(self) -> list[str]:
        with self._conn() as db:
            rows = db.execute("SELECT user_key FROM watchlist UNION SELECT user_key FROM holdings "
                              "UNION SELECT user_key FROM price_alerts WHERE triggered_at IS NULL").fetchall()
        return [r[0] for r in rows]

    # ---------------------------------------------------------------- price alerts the user sets
    def add_price_alert(self, user: str, ticker: str, direction: str, price: float) -> Optional[int]:
        """None when the user already has the maximum number of active alerts."""
        with self._conn() as db:
            n = db.execute("SELECT COUNT(*) FROM price_alerts WHERE user_key=? AND triggered_at IS NULL",
                           (user,)).fetchone()[0]
            if n >= MAX_PRICE_ALERTS:
                return None
            return db.insert_id("INSERT INTO price_alerts (user_key, ticker, direction, price, created_at) "
                                "VALUES (?,?,?,?,?)", (user, ticker, direction, price, _now()))

    def price_alerts(self, user: str) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT id, ticker, direction, price, created_at, triggered_at, triggered_price "
                              "FROM price_alerts WHERE user_key=? ORDER BY triggered_at IS NOT NULL, id DESC "
                              "LIMIT 60", (user,)).fetchall()
        return [dict(r) for r in rows]

    def active_price_alerts(self) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT id, user_key, ticker, direction, price FROM price_alerts "
                              "WHERE triggered_at IS NULL").fetchall()
        return [dict(r) for r in rows]

    def trigger_price_alert(self, alert_id: int, price: float) -> bool:
        with self._conn() as db:
            cur = db.execute("UPDATE price_alerts SET triggered_at=?, triggered_price=? "
                             "WHERE id=? AND triggered_at IS NULL", (_now(), price, alert_id))
            return cur.rowcount == 1

    def delete_price_alert(self, user: str, alert_id: int) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM price_alerts WHERE user_key=? AND id=?", (user, alert_id))

    # ---------------------------------------------------------------- Telegram
    def telegram_chat(self, user: str) -> Optional[str]:
        with self._conn() as db:
            row = db.execute("SELECT chat_id FROM telegram_links WHERE user_key=?", (user,)).fetchone()
        return row[0] if row else None

    def link_telegram(self, user: str, chat_id: str) -> None:
        with self._conn() as db:
            db.execute("INSERT OR REPLACE INTO telegram_links VALUES (?,?,?)", (user, str(chat_id), _now()))
            db.execute("DELETE FROM telegram_codes WHERE user_key=?", (user,))

    def unlink_telegram(self, user: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM telegram_links WHERE user_key=?", (user,))

    def new_telegram_code(self, user: str, code: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM telegram_codes WHERE user_key=?", (user,))
            db.execute("INSERT INTO telegram_codes VALUES (?,?,?)", (code, user, _now()))

    def user_for_code(self, code: str) -> Optional[str]:
        with self._conn() as db:
            row = db.execute("SELECT user_key, created_at FROM telegram_codes WHERE code=?", (code,)).fetchone()
        if not row:
            return None
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row[1])
        return row[0] if age.total_seconds() < 3600 else None

    # ---------------------------------------------------------------- briefs
    def save_brief(self, user: str, kind: str, day: str, data: dict) -> None:
        with self._conn() as db:
            db.execute("INSERT OR REPLACE INTO briefs VALUES (?,?,?,?,?)",
                       (user, kind, day, _now(), json.dumps(data, default=str)))

    def brief(self, user: str, kind: str, day: str) -> Optional[dict]:
        with self._conn() as db:
            row = db.execute("SELECT data, created_at FROM briefs WHERE user_key=? AND kind=? AND day=?",
                             (user, kind, day)).fetchone()
        return {**json.loads(row["data"]), "createdAt": row["created_at"]} if row else None

    def latest_brief(self, user: str, kind: str) -> Optional[dict]:
        with self._conn() as db:
            row = db.execute("SELECT data, created_at FROM briefs WHERE user_key=? AND kind=? "
                             "ORDER BY day DESC LIMIT 1", (user, kind)).fetchone()
        return {**json.loads(row["data"]), "createdAt": row["created_at"]} if row else None

    # ---------------------------------------------------------------- alerts
    def add_alert(self, user: str, ticker: str, kind: str, dedupe: str, title: str,
                  detail: str = "", tone: str = "neutral", link: str = "") -> bool:
        """True when the alert is new (the same dedupe key is stored only once per user)."""
        with self._conn() as db:
            cur = db.execute("INSERT OR IGNORE INTO alerts (user_key, ticker, kind, dedupe, title, detail, "
                             "tone, link, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                             (user, ticker, kind, dedupe, title, detail, tone, link, _now()))
            return cur.rowcount == 1

    def alerts(self, user: str, limit: int = 40) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT id, ticker, kind, title, detail, tone, link, created_at, seen "
                              "FROM alerts WHERE user_key=? ORDER BY id DESC LIMIT ?",
                              (user, limit)).fetchall()
        return [dict(r) for r in rows]

    def mark_seen(self, user: str) -> None:
        with self._conn() as db:
            db.execute("UPDATE alerts SET seen=1 WHERE user_key=?", (user,))

    # ---------------------------------------------------------------- settings and job bookkeeping
    def email_briefs(self, user: str) -> bool:
        with self._conn() as db:
            row = db.execute("SELECT email_briefs FROM notify_settings WHERE user_key=?", (user,)).fetchone()
        return bool(row and row[0])

    def set_email_briefs(self, user: str, on: bool) -> None:
        with self._conn() as db:
            db.execute("INSERT OR REPLACE INTO notify_settings VALUES (?,?)", (user, int(on)))

    def last_job(self, job: str) -> Optional[str]:
        with self._conn() as db:
            row = db.execute("SELECT last_run FROM job_runs WHERE job=?", (job,)).fetchone()
        return row[0] if row else None

    def mark_job(self, job: str, when: str) -> None:
        with self._conn() as db:
            db.execute("INSERT OR REPLACE INTO job_runs VALUES (?,?)", (job, when))
