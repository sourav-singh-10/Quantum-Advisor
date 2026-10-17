"""Test doubles: a scripted LLM and deterministic data tools (no network, no API keys)."""
from __future__ import annotations

import math
from collections import defaultdict

from services.llm_service import LLMResult, LLMStats


class FakeLLM:
    """Returns scripted answers per (agent, schema name). Each script entry is a dict (validated
    into the schema) or None (simulate an LLM failure). When a queue is empty the call fails,
    which makes the agent use its rule-based fallback, exactly like a missing API key."""

    def __init__(self, script: dict | None = None, available: bool = True):
        self.script = defaultdict(list, {k: list(v) for k, v in (script or {}).items()})
        self.available = available
        self.stats = LLMStats()
        self.calls: list[tuple[str, str, str]] = []
        self.systems: list[str] = []

    def structured(self, *, agent, system, prompt, schema, reasoning=False, temperature=0.2):
        self.stats.calls += 1
        key = (agent, schema.__name__)
        self.calls.append((agent, schema.__name__, prompt))
        self.systems.append(system)
        queue = self.script.get(key)
        if not self.available or not queue:
            self.stats.failures += 1
            return LLMResult(None, "fake", 0, "scripted failure")
        answer = queue.pop(0)
        if answer is None:
            self.stats.failures += 1
            return LLMResult(None, "fake", 0, "scripted failure")
        return LLMResult(schema.model_validate(answer), "fake", 1)


def price_series(n=120, start=100.0, drift=0.002, wobble=0.01):
    return [start * (1 + drift) ** i * (1 + wobble * math.sin(i)) for i in range(n)]


FUNDAMENTALS = {"pe": 20.0, "roe": 18.0, "de": 0.4, "profitMargin": 10.0, "sector": "Energy",
                "marketCapCr": 100000, "name": "Test Industries"}


def patch_data(monkeypatch, *, prices=None, failing_sources=(), fundamentals=None,
               headlines=None, failing_news=()):
    """Replace every network call with deterministic data."""
    from tools import fundamentals_data, market_data, news_data
    from tools.base import ToolError

    prices = prices if prices is not None else price_series()

    def fake_prices(source):
        def _f(symbol):
            if source in failing_sources:
                raise ToolError(f"{source} down (test)")
            return list(prices)
        return _f

    for src in market_data.SOURCES:
        monkeypatch.setitem(market_data._FETCHERS, src, fake_prices(src))

    def fake_fund(symbol):
        if fundamentals is None:
            raise ToolError("no fundamentals (test)")
        return dict(fundamentals)
    monkeypatch.setattr(fundamentals_data, "fetch_fundamentals", fake_fund)

    def fake_news(source):
        def _f(query):
            if source in failing_news or headlines is None:
                raise ToolError(f"{source} down (test)")
            return [{"title": t, "source": "test", "published": None} for t in headlines]
        return _f
    for src in news_data.SOURCES:
        monkeypatch.setitem(news_data._FETCHERS, src, fake_news(src))
