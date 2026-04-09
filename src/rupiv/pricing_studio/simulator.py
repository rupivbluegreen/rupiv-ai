"""What-if pricing simulation engine.

Loads historical events, calculates revenue under current and proposed pricing
rules using the stateless ``PricingEngine``, and returns a comparison.

ALL money arithmetic uses ``decimal.Decimal`` — never ``float``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.pricing import LineItem, PricingEngine, PricingModel, _round_money, _to_decimal
from rupiv.models.event import Event
from rupiv.models.plan import Plan, PricingRule

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class SimulationScenario(BaseModel):
    """Describes a what-if pricing scenario to test against historical data."""

    pricing_rules: list[dict[str, Any]] = Field(
        ..., description="Proposed pricing rules to simulate"
    )
    date_range: dict[str, str] = Field(
        ..., description="Start/end dates as ISO strings, e.g. {'start': '2026-01-01', 'end': '2026-03-31'}"
    )
    customer_ids: list[UUID] | None = Field(
        default=None, description="Optional filter to specific customers"
    )


@dataclass(frozen=True)
class SimulationResult:
    """Comparison of current vs. simulated revenue."""

    current_revenue: Decimal
    simulated_revenue: Decimal
    delta: Decimal
    delta_pct: Decimal
    billable_outcomes_current: int
    billable_outcomes_simulated: int
    affected_customers: int
    line_item_breakdown: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _InMemoryRule:
    """Lightweight rule object that satisfies ``PricingRuleLike`` protocol."""

    pricing_model: str
    metric: str | None = None
    flat_amount: Decimal | None = None
    unit_amount: Decimal | None = None
    outcome_rules: dict[str, Any] | None = None
    tiers: list[dict[str, Any]] | None = None


def _dict_to_rule(d: dict[str, Any]) -> _InMemoryRule:
    """Convert a raw dict (from scenario JSON) into a rule object."""
    return _InMemoryRule(
        pricing_model=d.get("model", d.get("pricing_model", "outcome")),
        metric=d.get("metric"),
        flat_amount=_to_decimal(d.get("flat_amount")),
        unit_amount=_to_decimal(d.get("unit_price", d.get("unit_amount", d.get("price_per_outcome")))),
        outcome_rules=d.get("outcome_rules"),
        tiers=d.get("tiers"),
    )


def _aggregate_events(
    events: list[Any],
    rules: list[Any],
) -> dict[str, dict[str, Any]]:
    """Build an aggregated dict keyed by metric from raw DB events.

    Groups usage events by count and outcome events into outcome lists,
    matching the format expected by ``PricingEngine.calculate_line_items``.
    """
    aggregated: dict[str, dict[str, Any]] = {}

    for rule in rules:
        metric = getattr(rule, "metric", None) or ""
        if metric not in aggregated:
            aggregated[metric] = {"quantity": Decimal("0"), "outcomes": []}

    for ev in events:
        metric = ev.metric or ""
        if metric not in aggregated:
            aggregated[metric] = {"quantity": Decimal("0"), "outcomes": []}

        if ev.event_type == "usage":
            aggregated[metric]["quantity"] += Decimal("1")
        elif ev.event_type == "outcome":
            aggregated[metric]["outcomes"].append(
                {"properties": ev.properties or {}}
            )

    return aggregated


def _count_billable_outcomes(line_items: list[LineItem]) -> int:
    """Sum billable outcome quantities from line items."""
    total = Decimal("0")
    for li in line_items:
        if li.pricing_model == PricingModel.OUTCOME:
            total += li.quantity
    return int(total)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_simulation(
    session: AsyncSession,
    scenario: SimulationScenario,
    plan_id: UUID,
) -> SimulationResult:
    """Run a what-if pricing simulation.

    1. Load the plan's current pricing rules from the database.
    2. Load historical events for the date range.
    3. Calculate revenue with current rules using ``PricingEngine``.
    4. Calculate revenue with the scenario's proposed rules.
    5. Return a ``SimulationResult`` comparing both.
    """
    engine = PricingEngine()

    # -- Load current plan + rules ------------------------------------------
    stmt = select(Plan).where(Plan.id == plan_id)
    result = await session.execute(stmt)
    plan: Plan | None = result.scalar_one_or_none()
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found")

    current_rules: list[PricingRule] = list(plan.pricing_rules)

    # -- Parse date range ---------------------------------------------------
    start_date = date.fromisoformat(scenario.date_range["start"])
    end_date = date.fromisoformat(scenario.date_range["end"])
    period = f"{start_date.isoformat()}_{end_date.isoformat()}"

    # -- Load historical events ---------------------------------------------
    event_stmt = select(Event).where(
        Event.timestamp >= start_date,
        Event.timestamp < end_date,
    )
    if scenario.customer_ids:
        event_stmt = event_stmt.where(Event.customer_id.in_(scenario.customer_ids))

    event_result = await session.execute(event_stmt)
    events = list(event_result.scalars().all())

    # Count unique affected customers
    customer_set: set[str] = set()
    for ev in events:
        customer_set.add(str(ev.customer_id))
    affected_customers = len(customer_set)

    log.info(
        "simulation.events_loaded",
        plan_id=str(plan_id),
        event_count=len(events),
        affected_customers=affected_customers,
        date_range=scenario.date_range,
    )

    # -- Calculate current revenue ------------------------------------------
    current_aggregated = _aggregate_events(events, current_rules)
    current_line_items = engine.calculate_line_items(current_rules, current_aggregated, period)
    current_revenue = sum((li.amount for li in current_line_items), Decimal("0"))

    # -- Calculate simulated revenue ----------------------------------------
    simulated_rules = [_dict_to_rule(d) for d in scenario.pricing_rules]
    simulated_aggregated = _aggregate_events(events, simulated_rules)
    simulated_line_items = engine.calculate_line_items(
        simulated_rules, simulated_aggregated, period
    )
    simulated_revenue = sum((li.amount for li in simulated_line_items), Decimal("0"))

    # -- Comparison ---------------------------------------------------------
    delta = simulated_revenue - current_revenue
    delta_pct = (
        _round_money((delta / current_revenue) * Decimal("100"))
        if current_revenue != Decimal("0")
        else Decimal("0")
    )

    billable_current = _count_billable_outcomes(current_line_items)
    billable_simulated = _count_billable_outcomes(simulated_line_items)

    breakdown: list[dict[str, Any]] = []
    for li in simulated_line_items:
        breakdown.append(
            {
                "description": li.description,
                "quantity": str(li.quantity),
                "unit_amount": str(li.unit_amount),
                "amount": str(li.amount),
                "metric": li.metric,
                "pricing_model": li.pricing_model.value,
            }
        )

    result_obj = SimulationResult(
        current_revenue=_round_money(current_revenue),
        simulated_revenue=_round_money(simulated_revenue),
        delta=_round_money(delta),
        delta_pct=delta_pct,
        billable_outcomes_current=billable_current,
        billable_outcomes_simulated=billable_simulated,
        affected_customers=affected_customers,
        line_item_breakdown=breakdown,
    )

    log.info(
        "simulation.complete",
        plan_id=str(plan_id),
        current_revenue=str(result_obj.current_revenue),
        simulated_revenue=str(result_obj.simulated_revenue),
        delta=str(result_obj.delta),
        delta_pct=str(result_obj.delta_pct),
    )

    return result_obj
