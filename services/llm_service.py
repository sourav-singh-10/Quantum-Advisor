"""Gemini client with structured (JSON-schema) output, retries, and honest failure reporting.

Transient errors (503 overloaded, 429 rate limit) are retried after a short wait. A model
that stays busy is skipped for a cooldown, so a run does not stall on every call; if a
fallback model is configured it is used instead. A retired model (404) or a bad key fails
immediately.

Agents never receive free text from here: every call names a Pydantic schema and gets back
either a validated object or ``None`` plus the reason, so the caller can fall back to its
rule-based tool and mark itself as degraded.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

import config

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult:
    value: Optional[BaseModel]
    model: str
    latency_ms: int
    error: Optional[str] = None
    attempts: int = 1


@dataclass
class LLMStats:
    calls: int = 0
    failures: int = 0
    by_agent: dict = field(default_factory=dict)
    models: dict = field(default_factory=dict)      # model -> successful calls in this run


class RateLimiter:
    """Sliding-window limiter for one model, shared by every call in the process (free-tier friendly)."""

    def __init__(self, per_minute: int):
        self.per_minute = max(1, per_minute)
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self, max_wait: float = 45.0) -> bool:
        deadline = time.monotonic() + max_wait
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] > 60:
                    self._calls.popleft()
                if len(self._calls) < self.per_minute:
                    self._calls.append(now)
                    return True
                sleep_for = 60 - (now - self._calls[0]) + 0.05
            if time.monotonic() + sleep_for > deadline:
                return False
            time.sleep(min(sleep_for, 1.0))


# Each Gemini model has its own free-tier quota, so each gets its own limiter: analysts on the
# fast model no longer queue behind the debate on the reasoning model.
_limiters: dict[str, RateLimiter] = {}
_limiters_lock = threading.Lock()


def _limiter_for(model: str) -> RateLimiter:
    with _limiters_lock:
        if model not in _limiters:
            _limiters[model] = RateLimiter(config.GEMINI_RPM)
        return _limiters[model]


_busy_until: dict[str, float] = {}       # model -> monotonic time it may be tried again
_busy_lock = threading.Lock()

TRANSIENT = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded", "high demand",
             "504", "DEADLINE_EXCEEDED", "500", "INTERNAL", "timed out", "Timeout",
             "ConnectionError")
QUOTA = ("429", "RESOURCE_EXHAUSTED")   # per-minute quota: waiting seconds will not help
PERMANENT = ("404", "NOT_FOUND", "API key", "API_KEY", "PERMISSION_DENIED", "403")


def _is_busy(model: str) -> bool:
    with _busy_lock:
        return time.monotonic() < _busy_until.get(model, 0)


def _mark_busy(model: str) -> None:
    with _busy_lock:
        _busy_until[model] = time.monotonic() + config.LLM_BUSY_COOLDOWN_SECONDS


class LLMClient:
    """Thin wrapper around google-genai. ``available`` is False when no key is configured."""

    def __init__(self, api_key: str | None = None, fast_model: str | None = None,
                 reasoning_model: str | None = None, timeout_s: int | None = None):
        self.api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self.fast_model = fast_model or config.GEMINI_FAST_MODEL
        self.reasoning_model = reasoning_model or config.GEMINI_REASONING_MODEL
        self.fallback_model = config.GEMINI_FALLBACK_MODEL
        self.timeout_s = timeout_s or config.LLM_TIMEOUT_SECONDS
        self._client = None
        self.stats = LLMStats()
        # requested model -> the model that answered last time. One client serves one analysis,
        # so once a busy model has been replaced, the rest of the run stays on its replacement
        # instead of switching back and forth (different models argue differently).
        self._route: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.genai import types
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=self.timeout_s * 1000),
            )
        return self._client

    def structured(self, *, agent: str, system: str, prompt: str, schema: Type[T],
                   reasoning: bool = False, temperature: float | None = None) -> LLMResult:
        model = self.reasoning_model if reasoning else self.fast_model
        temperature = config.LLM_TEMPERATURE if temperature is None else temperature
        self.stats.calls += 1
        self.stats.by_agent[agent] = self.stats.by_agent.get(agent, 0) + 1
        if not self.available:
            self.stats.failures += 1
            return LLMResult(None, model, 0, "GEMINI_API_KEY is not set")

        from google.genai import types
        started = time.monotonic()
        # Order: the model for this role, the configured backup, then the fast model, which
        # is the most likely to have free capacity when a bigger model is overloaded.
        candidates = [m for m in (self._route.get(model), model, self.fallback_model, self.fast_model) if m]
        candidates = list(dict.fromkeys(candidates))          # unique, in order
        last_error, attempts, transient_fails = None, 0, 0
        current = next((m for m in candidates if not _is_busy(m)), None)
        if current is None:
            self.stats.failures += 1
            return LLMResult(None, model, 0, f"{model} is busy or out of quota; skipping it for now")

        max_attempts = 1 + 2 * len(candidates)   # e.g. 3 models -> up to 7 tries
        while attempts < max_attempts and current:
            attempts += 1
            if not _limiter_for(current).wait(max_wait=config.LLM_QUEUE_SECONDS):
                last_error = f"local rate limit: {current}'s requests per minute are used up"
                nxt = next((m for m in candidates if m != current and not _is_busy(m)), None)
                if nxt is None:
                    break
                current = nxt
                continue
            try:
                response = self._get_client().models.generate_content(
                    model=current,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=temperature,
                        seed=config.LLM_SEED,
                    ),
                )
                value = schema.model_validate_json(response.text or "")
                self._route[model] = current
                self.stats.models[current] = self.stats.models.get(current, 0) + 1
                return LLMResult(value, current, int((time.monotonic() - started) * 1000),
                                 attempts=attempts)
            except ValidationError as exc:
                last_error = f"invalid JSON from model: {exc.errors()[0].get('msg', exc)}"
                if attempts >= 2:
                    break
            except Exception as exc:  # network, quota, overload, bad model name ...
                text = f"{type(exc).__name__}: {exc}"
                last_error = text[:300]
                nxt = next((m for m in candidates if m != current and not _is_busy(m)), None)
                if any(k in text for k in PERMANENT):
                    current = nxt                    # retired model or bad key: no point waiting
                    continue
                if not any(k in text for k in TRANSIENT):
                    if attempts >= 2:
                        break
                    continue
                transient_fails += 1
                # The main model gets a second try after a wait; a backup is skipped at once,
                # and so is any model whose per-minute quota is used up.
                limit = 1 if any(k in text for k in QUOTA) or current != candidates[0] else 2
                if transient_fails >= limit:        # stays busy: skip it for a while
                    _mark_busy(current)
                    current, transient_fails = nxt, 0
                    continue
                delays = config.LLM_RETRY_DELAYS or (0,)
                time.sleep(delays[min(transient_fails - 1, len(delays) - 1)])
        self.stats.failures += 1
        return LLMResult(None, current or model, int((time.monotonic() - started) * 1000),
                         last_error, attempts=attempts)

    def ping(self) -> dict:
        """Used by /api/health?deep=1 to prove the configured model actually answers."""

        class Pong(BaseModel):
            ok: bool

        result = self.structured(agent="Health", system="Reply with ok=true.",
                                 prompt="ping", schema=Pong)
        return {"llmAvailable": result.value is not None, "model": result.model,
                "latencyMs": result.latency_ms, "error": result.error}
