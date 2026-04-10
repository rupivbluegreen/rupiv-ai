"""Outbound webhook event dispatcher.

Pushes events to a Redis list for async delivery by the webhook worker.
Designed to be called from billing/payment code without blocking.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

WEBHOOK_QUEUE_KEY = "rupiv:webhooks:outbound"


async def dispatch_event(
    event_type: str,
    payload: dict[str, Any],
    redis_url: str | None = None,
) -> bool:
    """Push a webhook event to the Redis delivery queue.

    This is a fire-and-forget operation — if Redis is unavailable,
    the event is logged and dropped (not retried from the caller side).

    Args:
        event_type: Event type string, e.g. ``"invoice.paid"``.
        payload: Event data dict to include in the webhook body.
        redis_url: Optional Redis URL override (defaults to settings).

    Returns:
        ``True`` if the event was successfully queued.
    """
    message = {
        "event_type": event_type,
        "payload": payload,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    try:
        import redis.asyncio as aioredis

        if redis_url is None:
            from rupiv.config import get_settings

            redis_url = get_settings().REDIS_URL

        client: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=True)  # type: ignore[assignment]
        try:
            await client.rpush(WEBHOOK_QUEUE_KEY, json.dumps(message))
        finally:
            await client.aclose()

        log.info(
            "webhook.event_dispatched",
            event_type=event_type,
            queue=WEBHOOK_QUEUE_KEY,
        )
        return True

    except Exception:
        log.warning(
            "webhook.dispatch_failed",
            event_type=event_type,
            exc_info=True,
        )
        return False
