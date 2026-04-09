"""ClickHouse client setup and schema initialization."""

from __future__ import annotations

import structlog
from clickhouse_connect.driver.asyncclient import AsyncClient
from clickhouse_connect.driver.httputil import default_pool_manager

from rupiv.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

EVENTS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS {database}.events (
    event_id UUID,
    customer_id UUID,
    subscription_id Nullable(UUID),
    event_type Enum8('usage' = 1, 'outcome' = 2),
    metric LowCardinality(String),
    properties String,
    outcome_status Enum8('pending' = 0, 'validated' = 1, 'rejected' = 2),
    idempotency_key String,
    timestamp DateTime64(3),
    ingested_at DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (customer_id, metric, timestamp, event_id)
"""


async def get_clickhouse_client() -> AsyncClient:
    """Create and return an async ClickHouse client.

    Uses ``clickhouse-connect`` with settings from the application config.
    The caller is responsible for closing the client when done.
    """
    settings = get_settings()

    # Parse host and port from CLICKHOUSE_URL (e.g. "http://localhost:8123")
    url = settings.CLICKHOUSE_URL.replace("http://", "").replace("https://", "")
    parts = url.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 8123

    import clickhouse_connect

    client: AsyncClient = await clickhouse_connect.get_async_client(
        host=host,
        port=port,
        database=settings.CLICKHOUSE_DATABASE,
    )
    return client


async def init_clickhouse() -> None:
    """Create the events table in ClickHouse if it does not already exist.

    This should be called once during application startup. ClickHouse is
    append-only; we use ``ReplacingMergeTree`` with ``ingested_at`` so that
    duplicate rows (same ``event_id``) are collapsed during background merges.
    """
    settings = get_settings()
    client = await get_clickhouse_client()
    try:
        ddl = EVENTS_TABLE_DDL.format(database=settings.CLICKHOUSE_DATABASE)
        logger.info("clickhouse_init", action="creating_events_table")
        await client.command(ddl)
        logger.info("clickhouse_init", action="events_table_ready")
    finally:
        await client.close()
