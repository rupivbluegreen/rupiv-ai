"""Event ingestion and metering pipeline for Rupiv.ai.

Events flow: POST /v1/events -> PostgreSQL -> Redis queue -> ClickHouse.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from rupiv.config import get_settings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

EVENTS_QUEUE_KEY = "rupiv:events:queue"


async def ingest_event(
    customer_id: str,
    metric: str,
    value: float,
    properties: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    *,
    event_type: str = "usage",
    subscription_id: str | None = None,
) -> dict[str, Any]:
    """Accept an incoming event and push it to a Redis list for async processing.

    The event has already been persisted to PostgreSQL by the API endpoint.
    This function enqueues a lightweight JSON payload so the event_processor
    worker can batch-write to ClickHouse.

    If Redis is unavailable the event is still safe in PostgreSQL; we log a
    warning and return normally.

    Args:
        customer_id: UUID of the customer.
        metric: Metric identifier (e.g. ``"api_call"``, ``"ticket_resolved"``).
        value: Numeric value for the event.
        properties: Arbitrary key-value metadata.
        idempotency_key: Caller-supplied dedup key.
        event_type: ``"usage"`` or ``"outcome"``.
        subscription_id: Optional subscription UUID.

    Returns:
        The event payload dict that was enqueued (or would have been).
    """
    event_id = str(uuid4())
    now = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "event_id": event_id,
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "event_type": event_type,
        "metric": metric,
        "value": value,
        "timestamp": now.isoformat(),
        "properties": properties or {},
        "idempotency_key": idempotency_key or event_id,
    }

    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.REDIS_URL,
            decode_responses=True,
        )
        try:
            await redis_client.rpush(EVENTS_QUEUE_KEY, json.dumps(payload))
            log.info(
                "event.enqueued",
                event_id=event_id,
                customer_id=customer_id,
                metric=metric,
            )
        finally:
            await redis_client.aclose()
    except Exception:
        log.warning(
            "event.enqueue_failed",
            event_id=event_id,
            customer_id=customer_id,
            metric=metric,
            exc_info=True,
        )

    return payload


async def write_to_clickhouse(events: list[dict[str, Any]]) -> int:
    """Batch-insert event dicts into the ClickHouse ``events`` table.

    Uses the async ClickHouse client from ``rupiv.clickhouse``.

    Args:
        events: List of event dicts with keys matching the ClickHouse schema.

    Returns:
        The number of rows inserted.
    """
    if not events:
        return 0

    from rupiv.clickhouse import get_clickhouse_client

    client = await get_clickhouse_client()
    try:
        rows: list[list[Any]] = []
        for e in events:
            rows.append([
                e["event_id"],
                e["customer_id"],
                e.get("subscription_id") or None,
                e.get("event_type", "usage"),
                e["metric"],
                json.dumps(e.get("properties", {})),
                e.get("outcome_status", "pending"),
                e.get("idempotency_key", ""),
                e["timestamp"],
            ])

        columns = [
            "event_id",
            "customer_id",
            "subscription_id",
            "event_type",
            "metric",
            "properties",
            "outcome_status",
            "idempotency_key",
            "timestamp",
        ]

        await client.insert(
            "events",
            rows,
            column_names=columns,
        )

        log.info("clickhouse.batch_written", count=len(rows))
        return len(rows)
    except Exception:
        log.error("clickhouse.batch_write_failed", count=len(events), exc_info=True)
        raise
    finally:
        await client.close()
