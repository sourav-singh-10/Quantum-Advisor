"""Shared helpers for tools: a typed error, an HTTP getter with timeout, and a TTL cache."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

import requests

import config


class ToolError(Exception):
    """Raised by a tool when it cannot produce a result. Agents report it; they never crash."""


_cache: dict[tuple, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def cached(key: tuple, fn: Callable[[], Any], ttl: int | None = None) -> Any:
    ttl = config.DATA_CACHE_SECONDS if ttl is None else ttl
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def http_get_json(url: str, params: dict) -> dict:
    try:
        response = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ToolError(f"network error: {type(exc).__name__}") from exc
    try:
        return response.json()
    except ValueError as exc:
        raise ToolError(f"non-JSON response (HTTP {response.status_code})") from exc
