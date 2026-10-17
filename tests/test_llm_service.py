from types import SimpleNamespace
from typing import List, Literal

from pydantic import BaseModel

from services.llm_service import LLMClient


class Critique(BaseModel):
    verdict: Literal["approve", "revise", "veto"]
    reasoning: str
    objections: List[str] = []


class _Models:
    def __init__(self, replies):
        self.replies, self.configs = list(replies), []

    def generate_content(self, model, contents, config):
        self.configs.append(config)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


def client_with(replies):
    llm = LLMClient(api_key="test-key", fast_model="fast", reasoning_model="smart")
    models = _Models(replies)
    llm._client = SimpleNamespace(models=models)
    return llm, models


def test_structured_output_is_validated():
    llm, models = client_with(['{"verdict":"approve","reasoning":"fine","objections":[]}'])
    res = llm.structured(agent="RiskManager", system="s", prompt="p", schema=Critique,
                         reasoning=True)
    assert res.value.verdict == "approve" and res.model == "smart"
    assert models.configs[0].response_mime_type == "application/json"


def test_invalid_json_is_retried_once():
    llm, _ = client_with(['{"verdict":"maybe"}',
                          '{"verdict":"revise","reasoning":"x","objections":[]}'])
    res = llm.structured(agent="RiskManager", system="s", prompt="p", schema=Critique)
    assert res.value.verdict == "revise" and res.attempts == 2


def test_errors_are_reported_not_raised():
    llm, _ = client_with([RuntimeError("quota"), RuntimeError("quota")])
    res = llm.structured(agent="RiskManager", system="s", prompt="p", schema=Critique)
    assert res.value is None and "quota" in res.error
    assert llm.stats.failures == 1


def test_missing_key_means_unavailable():
    llm = LLMClient(api_key="")
    assert not llm.available
    assert llm.structured(agent="x", system="s", prompt="p", schema=Critique).value is None


def test_rate_limiter_blocks_beyond_free_tier_quota():
    from services.llm_service import RateLimiter
    limiter = RateLimiter(per_minute=2)
    assert limiter.wait() and limiter.wait()
    assert limiter.wait(max_wait=0) is False


import pytest

import config
from services import llm_service

BUSY = RuntimeError("ServerError: 503 UNAVAILABLE. This model is currently experiencing high demand.")
OK = '{"verdict":"approve","reasoning":"fine","objections":[]}'


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(config, "LLM_RETRY_DELAYS", (0,))
    monkeypatch.setattr(config, "GEMINI_RPM", 1000)
    llm_service._limiters.clear()
    llm_service._busy_until.clear()
    yield
    llm_service._busy_until.clear()
    llm_service._limiters.clear()


def test_overloaded_model_is_retried_after_a_wait():
    llm, models = client_with([BUSY, OK])
    res = llm.structured(agent="RiskManager", system="s", prompt="p", schema=Critique)
    assert res.value.verdict == "approve" and res.attempts == 2


def test_model_that_stays_busy_falls_back_to_the_backup_model(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODEL", "backup")
    llm, models = client_with([BUSY, BUSY, OK])
    res = llm.structured(agent="RiskManager", system="s", prompt="p", schema=Critique)
    assert res.value is not None and res.model == "backup"
    # the busy model is now skipped, so the next call goes straight to the backup
    llm2, models2 = client_with([OK])
    assert llm2.structured(agent="x", system="s", prompt="p", schema=Critique).model == "backup"


def test_busy_model_without_a_backup_fails_fast():
    llm, models = client_with([BUSY, BUSY])
    assert llm.structured(agent="x", system="s", prompt="p", schema=Critique).value is None
    llm2, models2 = client_with([])          # would raise if called
    res = llm2.structured(agent="x", system="s", prompt="p", schema=Critique)
    assert res.value is None and "out of quota" in res.error and models2.configs == []


def test_retired_model_switches_to_backup_immediately(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODEL", "backup")
    llm, models = client_with([RuntimeError("ClientError: 404 NOT_FOUND model retired"), OK])
    res = llm.structured(agent="x", system="s", prompt="p", schema=Critique)
    assert res.model == "backup" and res.attempts == 2


def test_busy_reasoning_model_uses_the_fast_model():
    llm, models = client_with([BUSY, BUSY, OK])
    res = llm.structured(agent="RiskManager", system="s", prompt="p", schema=Critique,
                         reasoning=True)
    assert res.value is not None and res.model == "fast"
    # later reasoning calls skip the busy model and go straight to the fast one
    llm2, models2 = client_with([OK])
    assert llm2.structured(agent="x", system="s", prompt="p", schema=Critique,
                           reasoning=True).model == "fast"


def test_first_call_reaches_the_fast_model_when_main_and_backup_are_busy(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODEL", "backup")
    llm, models = client_with([BUSY, BUSY, BUSY, OK])     # main x2, backup x1, fast ok
    res = llm.structured(agent="Planner", system="s", prompt="p", schema=Critique,
                         reasoning=True)
    assert res.value is not None and res.model == "fast" and res.attempts == 4


def test_quota_error_switches_model_at_once_without_waiting(monkeypatch):
    import time
    calls = []
    monkeypatch.setattr(time, "sleep", lambda s: calls.append(s))
    monkeypatch.setattr(config, "LLM_RETRY_DELAYS", (2,))
    quota = RuntimeError("ClientError: 429 RESOURCE_EXHAUSTED. Quota exceeded")
    llm, models = client_with([quota, OK])
    res = llm.structured(agent="Planner", system="s", prompt="p", schema=Critique, reasoning=True)
    assert res.model == "fast" and res.attempts == 2 and calls == []


def test_gateway_timeout_is_retried():
    llm, models = client_with([RuntimeError("ServerError: 504 DEADLINE_EXCEEDED"), OK])
    assert llm.structured(agent="x", system="s", prompt="p", schema=Critique).value is not None


def test_a_run_stays_on_the_model_that_answered_and_calls_are_deterministic(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODEL", "backup")
    llm, models = client_with([BUSY, BUSY, OK, OK])
    first = llm.structured(agent="Strategy", system="s", prompt="p", schema=Critique, reasoning=True)
    assert first.model == "backup"
    llm_service._busy_until.clear()                  # the main model is free again ...
    second = llm.structured(agent="Risk", system="s", prompt="p", schema=Critique, reasoning=True)
    assert second.model == "backup"                  # ... but this run keeps the model it started with
    assert llm.stats.models == {"backup": 2}
    cfg = models.configs[-1]
    assert cfg.temperature == 0 and cfg.seed == config.LLM_SEED


def test_each_model_has_its_own_quota(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_RPM", 1)
    monkeypatch.setattr(config, "LLM_QUEUE_SECONDS", 0)
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODEL", "backup")
    llm, models = client_with([OK, OK, OK])
    assert llm.structured(agent="a", system="s", prompt="p", schema=Critique).model == "fast"
    # the fast model's minute is used up, so the next call moves on instead of queueing or failing
    assert llm.structured(agent="b", system="s", prompt="p", schema=Critique, reasoning=True).value
    assert llm.structured(agent="c", system="s", prompt="p", schema=Critique).value is not None
