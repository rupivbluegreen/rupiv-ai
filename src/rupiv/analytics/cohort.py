"""Customer cohort analysis — retention tracking over time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.customer import Customer
from rupiv.models.plan import PricingRule
from rupiv.models.subscription import Subscription, SubscriptionStatus

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CohortEntry:
    """A single cell in a cohort retention table."""

    cohort_month: str
    month_offset: int
    customers: int
    retained: int
    retention_rate: Decimal
    mrr: Decimal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_month(month_str: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' into (year, month)."""
    parts = month_str.split("-")
    return int(parts[0]), int(parts[1])


def _add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    """Add *offset* months to (year, month)."""
    total = (year - 1) * 12 + (month - 1) + offset
    new_year = total // 12 + 1
    new_month = total % 12 + 1
    return new_year, new_month


def _month_label(year: int, month: int) -> str:
    """Format (year, month) as 'YYYY-MM'."""
    return f"{year:04d}-{month:02d}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def calculate_cohorts(
    session: AsyncSession,
    start_month: str,
    num_months: int = 12,
) -> list[CohortEntry]:
    """Calculate customer cohort retention from *start_month* over *num_months*.

    Customers are grouped by the month they were created.  For each subsequent
    month, we count how many still have an active subscription.
    """
    start_year, start_mo = _parse_month(start_month)

    entries: list[CohortEntry] = []

    for cohort_offset in range(num_months):
        cy, cm = _add_months(start_year, start_mo, cohort_offset)
        cohort_label = _month_label(cy, cm)
        cohort_start = datetime(cy, cm, 1, tzinfo=UTC)
        ny, nm = _add_months(cy, cm, 1)
        cohort_end = datetime(ny, nm, 1, tzinfo=UTC)

        # Customers created in this cohort month
        cust_q = select(Customer.id).where(
            and_(
                Customer.created_at >= cohort_start,
                Customer.created_at < cohort_end,
            ),
        )
        cust_result = await session.execute(cust_q)
        cohort_customer_ids = [row[0] for row in cust_result.all()]
        cohort_size = len(cohort_customer_ids)

        if cohort_size == 0:
            continue

        # For each subsequent month, check retention
        remaining_months = num_months - cohort_offset
        for month_offset in range(remaining_months):
            check_y, check_m = _add_months(cy, cm, month_offset)
            check_start = datetime(check_y, check_m, 1, tzinfo=UTC)
            next_y, next_m = _add_months(check_y, check_m, 1)
            check_end = datetime(next_y, next_m, 1, tzinfo=UTC)

            # Count customers with active subs in the check month
            retained_q = select(func.count(func.distinct(Subscription.customer_id))).where(
                and_(
                    Subscription.customer_id.in_(cohort_customer_ids),
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.current_period_start < check_end,
                    Subscription.current_period_end >= check_start,
                ),
            )
            retained_result = await session.execute(retained_q)
            retained = retained_result.scalar() or 0

            retention_rate = (
                (Decimal(str(retained)) / Decimal(str(cohort_size)) * Decimal("100")).quantize(
                    Decimal("0.01"),
                )
                if cohort_size > 0
                else Decimal("0")
            )

            # MRR for retained customers in the check month
            mrr_q = (
                select(func.coalesce(func.sum(PricingRule.flat_amount), 0))
                .select_from(Subscription)
                .join(PricingRule, PricingRule.plan_id == Subscription.plan_id)
                .where(
                    and_(
                        Subscription.customer_id.in_(cohort_customer_ids),
                        Subscription.status == SubscriptionStatus.ACTIVE,
                        Subscription.current_period_start < check_end,
                        Subscription.current_period_end >= check_start,
                    ),
                )
            )
            mrr_result = await session.execute(mrr_q)
            mrr = Decimal(str(mrr_result.scalar() or 0))

            entries.append(
                CohortEntry(
                    cohort_month=cohort_label,
                    month_offset=month_offset,
                    customers=cohort_size,
                    retained=retained,
                    retention_rate=retention_rate,
                    mrr=mrr,
                ),
            )

    log.info(
        "analytics.cohorts_calculated",
        start_month=start_month,
        num_months=num_months,
        entries=len(entries),
    )

    return entries
