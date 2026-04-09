"""ClickHouse aggregation queries for billing periods.

Uses the async ``clickhouse-connect`` client and parameterised queries
to aggregate usage counts and validated outcomes from ``rupiv.events``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from clickhouse_connect.driver.asyncclient import AsyncClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def aggregate_usage(
    client: AsyncClient,
    customer_id: str,
    metric: str,
    period_start: datetime,
    period_end: datetime,
) -> Decimal:
    """Count usage events for *metric* in ``[period_start, period_end)``.

    Args:
        client: An async ClickHouse client.
        customer_id: UUID string of the customer.
        metric: The metric name to aggregate.
        period_start: Inclusive start of the billing window.
        period_end: Exclusive end of the billing window.

    Returns:
        Aggregate count as a ``Decimal``.
    """
    query = """
        SELECT count(*) AS total
        FROM rupiv.events
        WHERE customer_id = {customer_id:String}
          AND metric      = {metric:String}
          AND event_type  = 'usage'
          AND timestamp  >= {period_start:DateTime64(3)}
          AND timestamp   < {period_end:DateTime64(3)}
    """

    result = await client.query(
        query,
        parameters={
            "customer_id": customer_id,
            "metric": metric,
            "period_start": period_start,
            "period_end": period_end,
        },
    )

    row = result.first_row if result.first_row else None
    total = Decimal(str(row[0])) if row else Decimal("0")

    log.info(
        "aggregation.usage",
        customer_id=customer_id,
        metric=metric,
        total=str(total),
    )
    return total


async def aggregate_outcomes(
    client: AsyncClient,
    customer_id: str,
    metric: str,
    period_start: datetime,
    period_end: datetime,
    status: str = "validated",
) -> list[dict[str, Any]]:
    """Fetch validated outcome events for *metric* in the billing period.

    Each returned dict contains ``event_id``, ``properties``, and
    ``timestamp`` columns from ClickHouse.

    Args:
        client: An async ClickHouse client.
        customer_id: UUID string of the customer.
        metric: The metric name to filter.
        period_start: Inclusive start of the billing window.
        period_end: Exclusive end of the billing window.
        status: Outcome status filter (default ``"validated"``).

    Returns:
        A list of dicts, one per matching outcome event.
    """
    query = """
        SELECT event_id, properties, timestamp
        FROM rupiv.events
        WHERE customer_id   = {customer_id:String}
          AND metric        = {metric:String}
          AND event_type    = 'outcome'
          AND outcome_status = {status:String}
          AND timestamp    >= {period_start:DateTime64(3)}
          AND timestamp     < {period_end:DateTime64(3)}
    """

    result = await client.query(
        query,
        parameters={
            "customer_id": customer_id,
            "metric": metric,
            "status": status,
            "period_start": period_start,
            "period_end": period_end,
        },
    )

    column_names: list[str] = result.column_names  # type: ignore[assignment]
    outcomes: list[dict[str, Any]] = [
        dict(zip(column_names, row)) for row in result.result_rows
    ]

    log.info(
        "aggregation.outcomes",
        customer_id=customer_id,
        metric=metric,
        status=status,
        count=len(outcomes),
    )
    return outcomes
