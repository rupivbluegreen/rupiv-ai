"""Event ingestion and metering pipeline for Rupiv.ai."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Event:
    """Immutable billing event."""

    event_id: str
    customer_id: str
    metric: str
    value: float
    timestamp: datetime
    properties: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None


async def ingest_event(
    customer_id: str,
    metric: str,
    value: float,
    properties: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> Event:
    """Accept an incoming event and enqueue it to BullMQ for async processing.

    Idempotency: if *idempotency_key* is provided, duplicate submissions
    within 24 h are silently dropped by the downstream worker.
    """
    event = Event(
        event_id=str(uuid4()),
        customer_id=customer_id,
        metric=metric,
        value=value,
        timestamp=datetime.now(timezone.utc),
        properties=properties or {},
        idempotency_key=idempotency_key,
    )

    log.info(
        "event.ingested",
        event_id=event.event_id,
        customer_id=customer_id,
        metric=metric,
        idempotency_key=idempotency_key,
    )

    # Enqueue to BullMQ via Redis (bullmq Python bindings)
    # The queue name matches the worker consumer in workers/event_processor.py
    from bullmq import Queue  # type: ignore[import-untyped]

    queue = Queue("billing-events")
    await queue.add(
        "process_event",
        {
            "event_id": event.event_id,
            "customer_id": event.customer_id,
            "metric": event.metric,
            "value": event.value,
            "timestamp": event.timestamp.isoformat(),
            "properties": event.properties,
            "idempotency_key": event.idempotency_key,
        },
        opts={"jobId": event.idempotency_key or event.event_id},
    )

    log.info("event.enqueued", event_id=event.event_id)
    return event


async def write_to_clickhouse(events: list[Event]) -> int:
    """Write a batch of events to ClickHouse.

    Returns the number of rows inserted.
    """
    if not events:
        return 0

    import clickhouse_connect  # type: ignore[import-untyped]

    client = clickhouse_connect.get_client()

    rows = [
        (
            e.event_id,
            e.customer_id,
            e.metric,
            e.value,
            e.timestamp,
            e.idempotency_key or "",
        )
        for e in events
    ]
    columns = [
        "event_id",
        "customer_id",
        "metric",
        "value",
        "timestamp",
        "idempotency_key",
    ]

    client.insert(
        "billing_events",
        rows,
        column_names=columns,
    )

    log.info("clickhouse.batch_written", count=len(rows))
    return len(rows)
