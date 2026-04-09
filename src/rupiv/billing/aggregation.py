"""ClickHouse aggregation queries for billing periods."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog

log = structlog.get_logger(__name__)


async def aggregate_usage(
    customer_id: str,
    metric: str,
    period_start: datetime,
    period_end: datetime,
) -> Decimal:
    """Query ClickHouse for the total usage count of *metric* within the
    billing period ``[period_start, period_end)``.

    Returns:
        Aggregate usage as a Decimal.
    """
    import clickhouse_connect  # type: ignore[import-untyped]

    client = clickhouse_connect.get_client()

    query = """
        SELECT coalesce(sum(value), 0) AS total
        FROM billing_events
        WHERE customer_id = {customer_id:String}
          AND metric      = {metric:String}
          AND timestamp   >= {period_start:DateTime64(3)}
          AND timestamp   <  {period_end:DateTime64(3)}
    """

    result = client.query(
        query,
        parameters={
            "customer_id": customer_id,
            "metric": metric,
            "period_start": period_start,
            "period_end": period_end,
        },
    )

    total = Decimal(str(result.first_row[0])) if result.first_row else Decimal("0")

    log.info(
        "aggregation.usage",
        customer_id=customer_id,
        metric=metric,
        total=str(total),
    )
    return total


async def aggregate_outcomes(
    customer_id: str,
    metric: str,
    period_start: datetime,
    period_end: datetime,
    status: str = "validated",
) -> list[dict[str, Any]]:
    """Query ClickHouse for validated outcomes of *metric* within the
    billing period.

    Returns:
        List of outcome dicts, each containing at least
        ``outcome_id``, ``status``, ``timestamp``, and any extra
        properties stored in the ``properties`` column.
    """
    import clickhouse_connect  # type: ignore[import-untyped]

    client = clickhouse_connect.get_client()

    query = """
        SELECT
            outcome_id,
            customer_id,
            metric,
            status,
            timestamp,
            properties
        FROM billing_outcomes
        WHERE customer_id = {customer_id:String}
          AND metric      = {metric:String}
          AND status      = {status:String}
          AND timestamp   >= {period_start:DateTime64(3)}
          AND timestamp   <  {period_end:DateTime64(3)}
    """

    result = client.query(
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
