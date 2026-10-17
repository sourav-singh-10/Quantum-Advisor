import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _pg_for_tests() -> str:
    """QA_TEST_DATABASE_URL runs the whole suite on Postgres, each test on an empty schema."""
    import os
    target = os.getenv("QA_TEST_DATABASE_URL", "")
    if target:
        from core import db
        db.reset_cache()
        with db.connect(target) as conn:
            conn.raw.execute("DROP SCHEMA public CASCADE")
            conn.raw.execute("CREATE SCHEMA public")
    return target


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Every test gets its own log dir and DB, no API keys, and an empty data cache."""
    import config
    from tools.base import clear_cache
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    for key in ("MARKETSTACK_API_KEY", "ALPHAVANTAGE_API_KEY", "NEWS_API_KEY", "GEMINI_API_KEY",
                "GEMINI_FALLBACK_MODEL"):
        monkeypatch.setattr(config, key, "")
    monkeypatch.setattr(config, "SYMBOL_PRECHECK", False)   # tests use made-up symbols
    monkeypatch.setattr(config, "DATABASE_URL", _pg_for_tests())
    clear_cache()
    yield
    clear_cache()
