import pytest

from agents.market_agent import MarketAnalyst
from tests.agent_helpers import make_ctx
from tests.fakes import patch_data
from tools.base import ToolError


def test_switches_to_another_source_after_failure(monkeypatch, tmp_path):
    patch_data(monkeypatch, failing_sources=("yfinance",))
    ctx, llm = make_ctx(tmp_path, {("MarketAnalyst", "ToolStep"): [
        {"thought": "free source first", "action": "get_price_history", "argument": "yfinance"},
        {"thought": "yfinance failed; alphavantage next", "action": "get_price_history",
         "argument": "alphavantage"}]})
    out = MarketAnalyst().run(ctx, "TESTCO")
    assert out["priceSource"] == "alphavantage"
    assert out["sourcesTried"] == ["yfinance", "alphavantage"]


def test_interpretation_comes_from_llm_but_numbers_from_tools(monkeypatch, tmp_path):
    patch_data(monkeypatch)
    ctx, _ = make_ctx(tmp_path, {
        ("MarketAnalyst", "ToolStep"): [{"thought": "t", "action": "get_price_history",
                                         "argument": "yfinance"}],
        ("MarketAnalyst", "MarketView"): [{"summary": "LLM view", "momentum": "Up",
                                           "data_quality": "Good"}]})
    out = MarketAnalyst().run(ctx, "TESTCO")
    assert out["marketSummary"] == "LLM view" and out["observations"] == 120


def test_all_sources_down_raises_tool_error(monkeypatch, tmp_path):
    patch_data(monkeypatch, failing_sources=("yfinance", "alphavantage", "marketstack"))
    ctx, _ = make_ctx(tmp_path, available=False)
    with pytest.raises(ToolError, match="no price source worked"):
        MarketAnalyst().run(ctx, "TESTCO")
