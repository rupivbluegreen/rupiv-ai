"""Outcome billing metrics — success rates, validation counts, revenue."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.event import Event, EventType, OutcomeStatus
from rupiv.models.invoice import InvoiceLineItem

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutcomeMetrics:
    """Aggregated outcome metrics for a single metric name."""

    metric: str
    total_events: int
    validated: int
    rejected: int
    pending: int
    success_rate: Decimal
    avg_value: Decimal
    total_revenue: Decimal


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def calculate_outcome_metrics(
    session: AsyncSession,
    customer_id: uuid.UUID | None,
    metric: str | None,
    period_start: date,
    period_end: date,
) -> list[OutcomeMetrics]:
    """Calculate outcome billing metrics grouped by metric name.

    Filters by *customer_id* and/or *metric* when provided.
    """
    start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)

    # Build filters
    filters = [
        Event.event_type == EventType.OUTCOME,
        Event.timestamp >= start_dt,
        Event.timestamp < end_dt,
    ]
    if customer_id is not None:
        filters.append(Event.customer_id == customer_id)
    if metric is not None:
        filters.append(Event.metric == metric)

    # Aggregate by metric
    q = (
        select(
            Event.metric,
            func.count(Event.id).label("total_events"),
            func.sum(
                case(
                    (Event.outcome_status == OutcomeStatus.VALIDATED, 1),
                    else_=0,
                )
            ).label("validated"),
            func.sum(
                case(
                    (Event.outcome_status == OutcomeStatus.REJECTED, 1),
                    else_=0,
                )
            ).label("rejected"),
            func.sum(
                case(
                    (Event.outcome_status == OutcomeStatus.PENDING, 1),
                    else_=0,
                )
            ).label("pending"),
        )
        .where(and_(*filters))
        .group_by(Event.metric)
    )

    result = await session.execute(q)
    rows = result.all()

    metrics_list: list[OutcomeMetrics] = []
    for row in rows:
        metric_name = row[0]
        total = int(row[1] or 0)
        validated = int(row[2] or 0)
        rejected = int(row[3] or 0)
        pending = int(row[4] or 0)

        success_rate = (
            (Decimal(str(validated)) / Decimal(str(total)) * Decimal("100")).quantize(
                Decimal("0.01")
            )
            if total > 0
            else Decimal("0")
        )

        # Get revenue from invoice line items for this metric in the period
        rev_filters = [
            InvoiceLineItem.metric == metric_name,
        ]
        rev_q = select(
            func.coalesce(func.sum(InvoiceLineItem.amount), 0),
            func.coalesce(func.count(InvoiceLineItem.id), 0),
        ).where(and_(*rev_filters))

        rev_result = await session.execute(rev_q)
        rev_row = rev_result.one()
        total_revenue = Decimal(str(rev_row[0]))
        line_count = int(rev_row[1])

        avg_value = (
            (total_revenue / Decimal(str(validated))).quantize(Decimal("0.0001"))
            if validated > 0
            else Decimal("0")
        )

        metrics_list.append(
            OutcomeMetrics(
                metric=metric_name,
                total_events=total,
                validated=validated,
                rejected=rejected,
                pending=pending,
                success_rate=success_rate,
                avg_value=avg_value,
                total_revenue=total_revenue,
            )
        )

    log.info(
        "analytics.outcome_metrics",
        period=f"{period_start.isoformat()}/{period_end.isoformat()}",
        metric_count=len(metrics_list),
    )

    return metrics_list
