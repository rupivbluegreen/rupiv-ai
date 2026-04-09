"""BullMQ consumer — processes ingested billing events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from rupiv.billing.metering import Event, write_to_clickhouse

log = structlog.get_logger(__name__)


async def process_event(job: Any) -> None:
    """Dequeue an event from BullMQ, persist to ClickHouse, and update
    the PostgreSQL event status.

    Idempotency: the job ID is the event's ``idempotency_key`` (or
    ``event_id``), so BullMQ guarantees at-most-once delivery per key.

    Args:
        job: A BullMQ ``Job`` instance whose ``data`` dict contains the
             serialised event payload.
    """
    data: dict[str, Any] = job.data  # type: ignore[union-attr]
    event_id: str = data["event_id"]

    log.info("worker.event_processor.start", event_id=event_id)

    # Reconstruct the Event domain object
    event = Event(
        event_id=event_id,
        customer_id=data["customer_id"],
        metric=data["metric"],
        value=data["value"],
        timestamp=datetime.fromisoformat(data["timestamp"]).replace(
            tzinfo=timezone.utc
        ),
        properties=data.get("properties", {}),
        idempotency_key=data.get("idempotency_key"),
    )

    # 1. Write to ClickHouse (analytical store)
    await write_to_clickhouse([event])

    # 2. Update PostgreSQL event status to "processed"
    # TODO: Replace with actual database call
    # async with get_db_session() as session:
    #     await session.execute(
    #         update(EventRecord)
    #         .where(EventRecord.event_id == event_id)
    #         .values(status="processed", processed_at=datetime.now(timezone.utc))
    #     )
    #     await session.commit()

    log.info("worker.event_processor.done", event_id=event_id)
