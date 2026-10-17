"""One database layer for SQLite (default, a local file) and Postgres (set DATABASE_URL).

The app's SQL is written once, in SQLite's dialect. For Postgres this module translates the
few differences: ``?`` placeholders, ``INSERT OR IGNORE`` / ``INSERT OR REPLACE``,
``AUTOINCREMENT`` and ``REAL`` columns. Rows support both ``row[0]`` and ``row["name"]`` on
either database. A free hosted Postgres (Neon, Supabase) keeps accounts, watchlists, holdings
and the track record across redeploys, which Render's free disk does not.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from typing import Any, Iterable, Optional

import config

try:                                     # only needed when DATABASE_URL points at Postgres
    import psycopg
    from psycopg import errors as pg_errors
except ImportError:                      # pragma: no cover - SQLite-only installs
    psycopg = None
    pg_errors = None

IntegrityError: tuple = (sqlite3.IntegrityError,) + ((psycopg.IntegrityError,) if psycopg else ())


def url() -> str:
    return (config.DATABASE_URL or "").strip()


def is_postgres(target: Optional[str] = None) -> bool:
    t = target if target is not None else url()
    return bool(t) and t.startswith(("postgres://", "postgresql://"))


# ------------------------------------------------------------------ Postgres rows and SQL
class Row:
    """Index or key access, and dict(row), like sqlite3.Row."""
    __slots__ = ("_names", "_values")

    def __init__(self, names: list[str], values: tuple):
        self._names, self._values = names, values

    def keys(self):
        return list(self._names)

    def __getitem__(self, k):
        if isinstance(k, (int, slice)):
            return self._values[k]
        return self._values[self._names.index(k)]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


def _row_factory(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: Row(names, values)


_columns_cache: dict[str, list[str]] = {}
_KEYS = {  # conflict targets for INSERT OR REPLACE
    "profiles": ("email",), "runs": ("run_id",), "briefs": ("user_key", "kind", "day"),
    "notify_settings": ("user_key",), "job_runs": ("job",), "telegram_links": ("user_key",),
    "watchlist": ("user_key", "ticker"), "holdings": ("user_key", "ticker"),
}


def translate(sql: str, columns_of=None) -> str:
    """SQLite SQL -> Postgres SQL for the statements this app uses."""
    s = sql
    s = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", s, flags=re.I)
    s = re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)
    m = re.match(r"\s*INSERT OR IGNORE INTO\s+(\w+)", s, re.I)
    if m:
        s = re.sub(r"INSERT OR IGNORE INTO", "INSERT INTO", s, count=1, flags=re.I).rstrip().rstrip(";")
        s += " ON CONFLICT DO NOTHING"
    m = re.match(r"\s*INSERT OR REPLACE INTO\s+(\w+)", s, re.I)
    if m:
        table = m.group(1)
        keys = _KEYS[table]
        cols = columns_of(table) if columns_of else []
        s = re.sub(r"INSERT OR REPLACE INTO\s+\w+", f"INSERT INTO {table}", s, count=1, flags=re.I)
        s = s.rstrip().rstrip(";")
        if cols and not re.search(rf"INSERT INTO {table}\s*\(", s, re.I):
            s = s.replace(f"INSERT INTO {table}", f"INSERT INTO {table} ({', '.join(cols)})", 1)
        updates = [c for c in cols if c not in keys]
        s += (f" ON CONFLICT ({', '.join(keys)}) DO UPDATE SET "
              + ", ".join(f"{c} = EXCLUDED.{c}" for c in updates)) if updates else \
             f" ON CONFLICT ({', '.join(keys)}) DO NOTHING"
    return s.replace("?", "%s")


# ------------------------------------------------------------------ connections
class Connection:
    """Thin wrapper so both databases look the same to the app."""

    def __init__(self, raw, postgres: bool, owned: bool = True):
        self.raw, self.postgres, self.owned = raw, postgres, owned

    def _columns(self, table: str) -> list[str]:
        if table not in _columns_cache:
            rows = self.raw.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s "
                "ORDER BY ordinal_position", (table,)).fetchall()
            _columns_cache[table] = [r[0] for r in rows]
        return _columns_cache[table]

    def execute(self, sql: str, params: Iterable[Any] = ()):
        if self.postgres:
            return self.raw.execute(translate(sql, self._columns), tuple(params))
        return self.raw.execute(sql, tuple(params))

    def executemany(self, sql: str, rows):
        if self.postgres:
            with self.raw.cursor() as cur:
                cur.executemany(translate(sql, self._columns), [tuple(r) for r in rows])
            return None
        return self.raw.executemany(sql, rows)

    def executescript(self, script: str):
        for stmt in [p.strip() for p in script.split(";") if p.strip()]:
            self.execute(stmt)

    def insert_id(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Run an INSERT and return the new row's id."""
        if self.postgres:
            return self.raw.execute(translate(sql, self._columns) + " RETURNING id", tuple(params)).fetchone()[0]
        return self.raw.execute(sql, tuple(params)).lastrowid

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.raw.commit()
            else:
                self.raw.rollback()
        finally:
            if self.owned:
                self.raw.close()
        return False


_local = threading.local()


def _pg_raw(target: str):
    """One open Postgres connection per thread, reopened if it was closed or broke."""
    conn = getattr(_local, "pg", None)
    if conn is None or conn.closed or conn.broken or getattr(_local, "pg_url", None) != target:
        conn = psycopg.connect(target, row_factory=_row_factory, connect_timeout=10)
        _local.pg, _local.pg_url = conn, target
    return conn


def connect(target: Optional[str] = None) -> Connection:
    """``target`` is a SQLite file path or a postgres:// URL; default: DATABASE_URL, else DB_PATH."""
    target = target if target is not None else (url() or config.DB_PATH)
    if is_postgres(target):
        if psycopg is None:
            raise RuntimeError("DATABASE_URL is set but psycopg is not installed")
        return Connection(_pg_raw(target), postgres=True, owned=False)
    raw = sqlite3.connect(target, timeout=10)
    raw.row_factory = sqlite3.Row
    return Connection(raw, postgres=False)


_ready: set = set()


def ensure_schema(name: str, target: Optional[str], create) -> None:
    """Run ``create(conn)`` once per process for each database (tables are created lazily)."""
    key = (name, target if target is not None else (url() or config.DB_PATH))
    if key in _ready:
        return
    with connect(target) as conn:
        create(conn)
    _ready.add(key)


def reset_cache() -> None:
    _columns_cache.clear()
    _ready.clear()
