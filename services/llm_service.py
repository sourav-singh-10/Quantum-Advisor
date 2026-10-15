"""Gemini client with structured (JSON-schema) output, one retry, and honest failure reporting.

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


class RateLimiter:
    """Sliding-window limiter shared by every LLM call in the process (free-tier friendly)."""

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


_limiter = RateLimiter(config.GEMINI_RPM)


class LLMClient:
    """Thin wrapper around google-genai. ``available`` is False when no key is configured."""

    def __init__(self, api_key: str | None = None, fast_model: str | None = None,
                 reasoning_model: str | None = None, timeout_s: int | None = None):
        self.api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self.fast_model = fast_model or config.GEMINI_FAST_MODEL
        self.reasoning_model = reasoning_model or config.GEMINI_REASONING_MODEL
        self.timeout_s = timeout_s or config.LLM_TIMEOUT_SECONDS
        self._client = None
        self.stats = LLMStats()

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
                   reasoning: bool = False, temperature: float = 0.2) -> LLMResult:
        model = self.reasoning_model if reasoning else self.fast_model
        self.stats.calls += 1
        self.stats.by_agent[agent] = self.stats.by_agent.get(agent, 0) + 1
        if not self.available:
            self.stats.failures += 1
            return LLMResult(None, model, 0, "GEMINI_API_KEY is not set")

        from google.genai import types
        started = time.monotonic()
        last_error = None
        for attempt in (1, 2):
            if not _limiter.wait():
                last_error = "local rate limit: free-tier requests per minute used up"
                break
            try:
                response = self._get_client().models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=temperature,
                    ),
                )
                value = schema.model_validate_json(response.text or "")
                return LLMResult(value, model, int((time.monotonic() - started) * 1000),
                                 attempts=attempt)
            except ValidationError as exc:
                last_error = f"invalid JSON from model: {exc.errors()[0].get('msg', exc)}"
            except Exception as exc:  # network, quota, bad model name ...
                last_error = f"{type(exc).__name__}: {exc}"[:300]
        self.stats.failures += 1
        return LLMResult(None, model, int((time.monotonic() - started) * 1000),
                         last_error, attempts=2)

    def ping(self) -> dict:
        """Used by /api/health?deep=1 to prove the configured model actually answers."""

        class Pong(BaseModel):
            ok: bool

        result = self.structured(agent="Health", system="Reply with ok=true.",
                                 prompt="ping", schema=Pong)
        return {"llmAvailable": result.value is not None, "model": result.model,
                "latencyMs": result.latency_ms, "error": result.error}
