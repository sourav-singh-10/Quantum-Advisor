import pytest

import config
from tools import market_data
from tools.base import ToolError


def test_marketstack_needs_a_key():
    with pytest.raises(ToolError, match="MARKETSTACK_API_KEY"):
        market_data.fetch_marketstack("TCS")


def test_marketstack_rows_are_returned_oldest_first(monkeypatch):
    monkeypatch.setattr(config, "MARKETSTACK_API_KEY", "k")
    monkeypatch.setattr(market_data, "http_get_json",
                        lambda url, params: {"data": [{"close": 3}, {"close": 2}, {"close": 1}]})
    assert market_data.fetch_marketstack("TCS") == [1.0, 2.0, 3.0]


def test_alphavantage_quota_message_is_surfaced(monkeypatch):
    monkeypatch.setattr(config, "ALPHAVANTAGE_API_KEY", "k")
    monkeypatch.setattr(market_data, "http_get_json",
                        lambda url, params: {"Note": "API call frequency exceeded"})
    with pytest.raises(ToolError, match="frequency"):
        market_data.fetch_alphavantage("TCS")


def test_unknown_source_is_rejected():
    with pytest.raises(ToolError, match="unknown source"):
        market_data.get_price_history("TCS", "bloomberg")


def test_short_history_is_rejected(monkeypatch):
    monkeypatch.setitem(market_data._FETCHERS, "yfinance", lambda s: [1.0] * 5)
    with pytest.raises(ToolError, match="only 5"):
        market_data.get_price_history("TCS", "yfinance")


def test_results_are_cached(monkeypatch):
    calls = []
    monkeypatch.setitem(market_data._FETCHERS, "yfinance",
                        lambda s: calls.append(s) or [1.0] * 30)
    market_data.get_price_history("TCS", "yfinance")
    market_data.get_price_history("TCS", "yfinance")
    assert calls == ["TCS"]


def test_free_sources_come_first():
    assert market_data.SOURCES[0] == "yfinance"
