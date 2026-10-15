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
