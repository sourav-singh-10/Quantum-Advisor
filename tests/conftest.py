import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Every test gets its own log dir and DB, no API keys, and an empty data cache."""
    import config
    from tools.base import clear_cache
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    for key in ("MARKETSTACK_API_KEY", "ALPHAVANTAGE_API_KEY", "NEWS_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setattr(config, key, "")
    clear_cache()
    yield
    clear_cache()
