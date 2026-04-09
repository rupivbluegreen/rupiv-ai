"""A/B test pricing models on live traffic.

Deterministic variant assignment uses a hash of ``customer_id + test_id``
so that a customer always sees the same variant for a given test.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.pricing import PricingEngine, _round_money
from rupiv.models.event import Event
from rupiv.models.plan import Plan

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass
class ABTest:
    """Definition of a pricing A/B test."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    control_plan_id: UUID = field(default_factory=uuid4)
    variant_plan_id: UUID = field(default_factory=uuid4)
    traffic_split: Decimal = Decimal("0.20")  # 20% variant
    status: str = "draft"  # draft | running | completed
    start_date: date | None = None
    end_date: date | None = None
    winner: str | None = None


def assign_variant(customer_id: UUID, ab_test: ABTest) -> str:
    """Deterministically assign a customer to 'control' or 'variant'.

    Uses SHA-256 of ``customer_id + test_id`` converted to a fraction in
    ``[0, 1)``.  If the fraction is below ``traffic_split``, the customer
    is assigned to the variant; otherwise to the control.
    """
    raw = f"{customer_id}:{ab_test.id}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    # Take the first 8 hex chars (32 bits) and normalize to [0, 1)
    hash_int = int(digest[:8], 16)
    fraction = Decimal(hash_int) / Decimal(2**32)

    assignment = "variant" if fraction < ab_test.traffic_split else "control"

    log.debug(
        "ab_test.assignment",
        customer_id=str(customer_id),
        test_id=str(ab_test.id),
        fraction=str(fraction),
        assignment=assignment,
    )
    return assignment


async def evaluate_test(
    session: AsyncSession,
    ab_test: ABTest,
) -> dict[str, Any]:
    """Compare metrics between control and variant groups.

    Loads events within the test period, splits customers by their
    deterministic assignment, and computes MRR, event counts, and
    unique customer counts for each arm.

    Returns a dict with ``control`` and ``variant`` sub-dicts plus a
    ``recommendation`` string.
    """
    engine = PricingEngine()

    # -- Load both plans ---------------------------------------------------
    control_plan = (
        await session.execute(select(Plan).where(Plan.id == ab_test.control_plan_id))
    ).scalar_one_or_none()
    variant_plan = (
        await session.execute(select(Plan).where(Plan.id == ab_test.variant_plan_id))
    ).scalar_one_or_none()

    if control_plan is None or variant_plan is None:
        raise ValueError("Control or variant plan not found")

    # -- Load events in test period ----------------------------------------
    event_stmt = select(Event)
    if ab_test.start_date:
        event_stmt = event_stmt.where(Event.timestamp >= ab_test.start_date)
    if ab_test.end_date:
        event_stmt = event_stmt.where(Event.timestamp < ab_test.end_date)

    event_result = await session.execute(event_stmt)
    events = list(event_result.scalars().all())

    # -- Split customers by assignment -------------------------------------
    control_customers: set[str] = set()
    variant_customers: set[str] = set()
    control_events: list[Any] = []
    variant_events: list[Any] = []

    for ev in events:
        cid = ev.customer_id
        if isinstance(cid, str):
            cid_uuid = UUID(cid)
        else:
            cid_uuid = cid

        arm = assign_variant(cid_uuid, ab_test)
        if arm == "control":
            control_customers.add(str(cid))
            control_events.append(ev)
        else:
            variant_customers.add(str(cid))
            variant_events.append(ev)

    # -- Compute per-arm metrics -------------------------------------------
    def _compute_revenue(plan: Plan, arm_events: list[Any]) -> Decimal:
        aggregated: dict[str, dict[str, Any]] = {}
        for rule in plan.pricing_rules:
            metric = rule.metric or ""
            if metric not in aggregated:
                aggregated[metric] = {"quantity": Decimal("0"), "outcomes": []}

        for ev in arm_events:
            metric = ev.metric or ""
            if metric not in aggregated:
                aggregated[metric] = {"quantity": Decimal("0"), "outcomes": []}
            if ev.event_type == "usage":
                aggregated[metric]["quantity"] += Decimal("1")
            elif ev.event_type == "outcome":
                aggregated[metric]["outcomes"].append({"properties": ev.properties or {}})

        period = "ab_test"
        line_items = engine.calculate_line_items(list(plan.pricing_rules), aggregated, period)
        return sum((li.amount for li in line_items), Decimal("0"))

    control_revenue = _compute_revenue(control_plan, control_events)
    variant_revenue = _compute_revenue(variant_plan, variant_events)

    # Normalize revenue per customer for fair comparison
    control_per_customer = (
        _round_money(control_revenue / Decimal(len(control_customers)))
        if control_customers
        else Decimal("0")
    )
    variant_per_customer = (
        _round_money(variant_revenue / Decimal(len(variant_customers)))
        if variant_customers
        else Decimal("0")
    )

    # -- Recommendation ----------------------------------------------------
    if variant_per_customer > control_per_customer:
        recommendation = "variant"
    elif control_per_customer > variant_per_customer:
        recommendation = "control"
    else:
        recommendation = "no_difference"

    result: dict[str, Any] = {
        "control": {
            "plan_id": str(ab_test.control_plan_id),
            "customers": len(control_customers),
            "events": len(control_events),
            "total_revenue": str(_round_money(control_revenue)),
            "revenue_per_customer": str(control_per_customer),
        },
        "variant": {
            "plan_id": str(ab_test.variant_plan_id),
            "customers": len(variant_customers),
            "events": len(variant_events),
            "total_revenue": str(_round_money(variant_revenue)),
            "revenue_per_customer": str(variant_per_customer),
        },
        "recommendation": recommendation,
    }

    log.info(
        "ab_test.evaluated",
        test_id=str(ab_test.id),
        control_customers=len(control_customers),
        variant_customers=len(variant_customers),
        recommendation=recommendation,
    )

    return result
