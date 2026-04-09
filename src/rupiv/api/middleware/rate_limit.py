"""Token-bucket rate limiting — Redis-backed with in-memory fallback."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

import structlog
from fastapi import HTTPException, Request, Response, status

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Default limits (requests per window)
# ---------------------------------------------------------------------------
DEFAULT_EVENT_LIMIT: int = 1000  # /v1/events
DEFAULT_LIMIT: int = 100  # everything else
DEFAULT_WINDOW: int = 60  # seconds


# ---------------------------------------------------------------------------
# In-memory fallback (single-process only, used when Redis is unavailable)
# ---------------------------------------------------------------------------
_mem_store: dict[str, dict[str, Any]] = defaultdict(dict)


def _in_memory_increment(bucket_key: str, window: int) -> tuple[int, int]:
    """Increment the counter for *bucket_key* in the in-memory store.

    Returns ``(current_count, ttl_remaining)``.
    """
    now = int(time.time())
    window_ts = now // window * window
    full_key = f"{bucket_key}:{window_ts}"

    entry = _mem_store.get(full_key)
    if entry is None or entry.get("expires_at", 0) <= now:
        _mem_store[full_key] = {"count": 1, "expires_at": window_ts + window}
        return 1, window
    entry["count"] += 1
    ttl = entry["expires_at"] - now
    return entry["count"], max(ttl, 1)


# ---------------------------------------------------------------------------
# Redis-backed counter
# ---------------------------------------------------------------------------


async def _redis_increment(
    redis: Any,
    bucket_key: str,
    window: int,
) -> tuple[int, int]:
    """Increment a counter in Redis and return ``(current_count, ttl)``.

    Key schema: ``rupiv:ratelimit:{bucket_key}:{window_timestamp}``
    """
    now = int(time.time())
    window_ts = now // window * window
    full_key = f"rupiv:ratelimit:{bucket_key}:{window_ts}"

    pipe = redis.pipeline()
    pipe.incr(full_key)
    pipe.ttl(full_key)
    results = await pipe.execute()

    current_count: int = results[0]
    ttl: int = results[1]

    # Set TTL on first increment (ttl == -1 means no expiry yet)
    if ttl == -1:
        await redis.expire(full_key, window + 1)
        ttl = window

    return current_count, max(ttl, 1)


# ---------------------------------------------------------------------------
# Core rate-limit check
# ---------------------------------------------------------------------------


async def check_rate_limit(
    request: Request,
    response: Response,
    key: str,
    limit: int = DEFAULT_LIMIT,
    window: int = DEFAULT_WINDOW,
) -> None:
    """Enforce a rate limit for *key*.

    Adds ``X-RateLimit-*`` headers to *response* and raises ``429`` when the
    limit is exceeded.

    Args:
        request: The current FastAPI request (used to access ``app.state.redis``).
        response: The current FastAPI response (rate-limit headers are set here).
        key: Unique identifier for the bucket (typically the API key hash).
        limit: Maximum number of requests allowed per *window*.
        window: Length of the rate-limit window in seconds.
    """
    redis = getattr(request.app.state, "redis", None)

    if redis is not None:
        try:
            current, ttl = await _redis_increment(redis, key, window)
        except Exception:
            logger.warning("rate_limit_redis_error_fallback_to_memory", key=key)
            current, ttl = _in_memory_increment(key, window)
    else:
        current, ttl = _in_memory_increment(key, window)

    remaining = max(limit - current, 0)
    reset_at = int(time.time()) + ttl

    # Always attach rate-limit headers
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_at)

    if current > limit:
        logger.warning(
            "rate_limit_exceeded",
            key=key,
            limit=limit,
            current=current,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={
                "Retry-After": str(ttl),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_at),
            },
        )


# ---------------------------------------------------------------------------
# Convenience FastAPI dependencies
# ---------------------------------------------------------------------------


async def rate_limit_events(
    request: Request,
    response: Response,
) -> None:
    """Rate-limit dependency for the event-ingestion endpoint (1000 req/min)."""
    api_key = getattr(getattr(request, "state", None), "api_key", None)
    key = api_key.key_hash if api_key is not None else "anonymous"
    await check_rate_limit(
        request, response, key=key, limit=DEFAULT_EVENT_LIMIT, window=DEFAULT_WINDOW,
    )


async def rate_limit_default(
    request: Request,
    response: Response,
) -> None:
    """Rate-limit dependency for standard endpoints (100 req/min)."""
    api_key = getattr(getattr(request, "state", None), "api_key", None)
    key = api_key.key_hash if api_key is not None else "anonymous"
    await check_rate_limit(request, response, key=key, limit=DEFAULT_LIMIT, window=DEFAULT_WINDOW)
