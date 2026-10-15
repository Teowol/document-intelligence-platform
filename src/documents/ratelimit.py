"""Lightweight, Redis-backed rate limiting (Phase 9).

Uses Django's cache (Redis in dev/prod, LocMem in tests) so no extra
dependency is needed. Good for throttling LLM-paid endpoints (QA/search).
"""

from __future__ import annotations

from time import time

from django.core.cache import cache
from django.core.exceptions import PermissionDenied


def is_rate_limited(user, *, key: str, limit: int, window: int = 60) -> bool:
    """Return True if `user` exceeded `limit` hits of `key` in `window` seconds.

    Uses a fixed-window counter cached by user+key. Cheap and good enough for
    coarse per-user throttling without Redis-specific data structures.
    """
    cache_key = f"ratelimit:{user.pk}:{key}"
    now = int(time())
    window_start = now // window * window  # align to whole windows

    # Re-read fresh: some runtimes race, but worst case is one extra call.
    data = cache.get(cache_key) or {}
    if data.get("window") != window_start:
        data = {"window": window_start, "count": 0}

    data["count"] += 1
    cache.set(cache_key, data, timeout=window * 2)

    return data["count"] > limit


def require_rate_limit(user, *, key: str, limit: int, window: int = 60) -> None:
    """Raise PermissionDenied(429) if the user exceeded the limit."""
    if is_rate_limited(user, key=key, limit=limit, window=window):
        raise PermissionDenied("Too many requests. Please wait and retry.")
