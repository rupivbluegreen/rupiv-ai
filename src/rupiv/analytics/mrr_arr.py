"""MRR / ARR / churn calculations from subscription data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.plan import BillingInterval, PricingRule
from rupiv.models.subscription import Subscription, SubscriptionStatus

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MRRResult:
    """Breakdown of Monthly Recurring Revenue for a period."""

    total_mrr: Decimal
    new_mrr: Decimal
    expansion_mrr: Decimal
    contraction_mrr: Decimal
    churned_mrr: Decimal
    net_new_mrr: Decimal
    customer_count: int
    period: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _monthly_equivalent(amount: Decimal | None, interval: BillingInterval | None) -> Decimal:
    """Convert a plan amount to its monthly equivalent."""
    if amount is None:
        return Decimal("0")
    if interval == BillingInterval.YEARLY:
        return (Decimal(str(amount)) / Decimal("12")).quantize(Decimal("0.0001"))
    return Decimal(str(amount))


def _month_start(d: date) -> datetime:
    """Return the first moment of the month containing *d* (UTC)."""
    return datetime(d.year, d.month, 1, tzinfo=timezone.utc)


def _month_end(d: date) -> datetime:
    """Return the first moment of the *next* month (exclusive upper bound)."""
    if d.month == 12:
        return datetime(d.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(d.year, d.month + 1, 1, tzinfo=timezone.utc)


def _prev_month_start(d: date) -> datetime:
    """Return the start of the previous month."""
    if d.month == 1:
        return datetime(d.year - 1, 12, 1, tzinfo=timezone.utc)
    return datetime(d.year, d.month - 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def calculate_mrr(session: AsyncSession, as_of_date: date) -> MRRResult:
    """Calculate MRR breakdown for the month containing *as_of_date*.

    * **total_mrr** — sum of monthly-equivalent plan amounts for active subs
    * **new_mrr** — subscriptions created this month
    * **churned_mrr** — subscriptions canceled this month
    * **expansion_mrr / contraction_mrr** — plan changes vs. previous month
    * **net_new_mrr** — new + expansion - contraction - churned
    """
    month_start = _month_start(as_of_date)
    month_end = _month_end(as_of_date)
    prev_start = _prev_month_start(as_of_date)

    period_label = as_of_date.strftime("%Y-%m")

    # ---- Active subscriptions (total MRR + customer count) -----------------
    active_q = (
        select(Subscription)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
        .where(Subscription.current_period_start < month_end)
    )
    active_result = await session.execute(active_q)
    active_subs = active_result.scalars().all()

    # Need plan info — eagerly loaded via selectin
    total_mrr = Decimal("0")
    customer_ids: set[str] = set()
    for sub in active_subs:
        plan = sub.plan
        for rule in plan.pricing_rules:
            total_mrr += _monthly_equivalent(rule.flat_amount, rule.billing_interval)
        customer_ids.add(str(sub.customer_id))

    # ---- New MRR (created this month) --------------------------------------
    new_q = (
        select(Subscription)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
        .where(Subscription.created_at >= month_start)
        .where(Subscription.created_at < month_end)
    )
    new_result = await session.execute(new_q)
    new_subs = new_result.scalars().all()

    new_mrr = Decimal("0")
    for sub in new_subs:
        for rule in sub.plan.pricing_rules:
            new_mrr += _monthly_equivalent(rule.flat_amount, rule.billing_interval)

    # ---- Churned MRR (canceled this month) ---------------------------------
    churned_q = (
        select(Subscription)
        .where(Subscription.status == SubscriptionStatus.CANCELED)
        .where(Subscription.canceled_at >= month_start)
        .where(Subscription.canceled_at < month_end)
    )
    churned_result = await session.execute(churned_q)
    churned_subs = churned_result.scalars().all()

    churned_mrr = Decimal("0")
    for sub in churned_subs:
        for rule in sub.plan.pricing_rules:
            churned_mrr += _monthly_equivalent(rule.flat_amount, rule.billing_interval)

    # ---- Expansion / contraction (plan changes vs previous month) ----------
    # Compare active subs that existed last month too — if their plan amount
    # changed, that delta is expansion (positive) or contraction (negative).
    prev_q = (
        select(Subscription)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
        .where(Subscription.created_at < prev_start)
        .where(Subscription.current_period_start < month_end)
    )
    prev_result = await session.execute(prev_q)
    prev_subs = prev_result.scalars().all()

    expansion_mrr = Decimal("0")
    contraction_mrr = Decimal("0")

    # For MVP, expansion/contraction requires comparing current plan amount to
    # a stored snapshot.  Without a plan-change log we approximate as zero for
    # subscriptions that have not changed plan.  A real implementation would
    # join on a subscription_plan_changes audit table.
    # Placeholder: expansion/contraction remain Decimal("0") until audit table exists.

    net_new_mrr = new_mrr + expansion_mrr - contraction_mrr - churned_mrr

    result = MRRResult(
        total_mrr=total_mrr,
        new_mrr=new_mrr,
        expansion_mrr=expansion_mrr,
        contraction_mrr=contraction_mrr,
        churned_mrr=churned_mrr,
        net_new_mrr=net_new_mrr,
        customer_count=len(customer_ids),
        period=period_label,
    )

    log.info(
        "analytics.mrr_calculated",
        period=period_label,
        total_mrr=str(total_mrr),
        customer_count=len(customer_ids),
    )

    return result


async def calculate_arr(session: AsyncSession, as_of_date: date) -> Decimal:
    """Calculate Annual Recurring Revenue — MRR * 12."""
    mrr = await calculate_mrr(session, as_of_date)
    return mrr.total_mrr * Decimal("12")


async def calculate_churn_rate(
    session: AsyncSession,
    period_start: date,
    period_end: date,
) -> Decimal:
    """Calculate customer churn rate for the given period.

    churn_rate = churned_in_period / active_at_period_start
    Returns a Decimal between 0 and 1 (or 0 if no customers).
    """
    start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)

    # Active at period start
    active_at_start_q = select(func.count(Subscription.id)).where(
        and_(
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED]),
            Subscription.created_at < start_dt,
        )
    )
    active_at_start_result = await session.execute(active_at_start_q)
    active_at_start: int = active_at_start_result.scalar() or 0

    if active_at_start == 0:
        return Decimal("0")

    # Churned during period
    churned_q = select(func.count(Subscription.id)).where(
        and_(
            Subscription.status == SubscriptionStatus.CANCELED,
            Subscription.canceled_at >= start_dt,
            Subscription.canceled_at < end_dt,
        )
    )
    churned_result = await session.execute(churned_q)
    churned: int = churned_result.scalar() or 0

    rate = (Decimal(str(churned)) / Decimal(str(active_at_start))).quantize(Decimal("0.0001"))

    log.info(
        "analytics.churn_rate",
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        active_at_start=active_at_start,
        churned=churned,
        rate=str(rate),
    )

    return rate
