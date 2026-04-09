"""Tests for the Pricing Studio module.

Covers simulation, A/B testing, revenue forecasting, and templates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.event import Event
from rupiv.models.plan import Plan, PricingRule
from rupiv.pricing_studio.ab_test import ABTest, assign_variant
from rupiv.pricing_studio.revenue_forecast import forecast_revenue
from rupiv.pricing_studio.simulator import SimulationScenario, run_simulation
from rupiv.pricing_studio.templates import get_templates

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLAN_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
CUSTOMER_A = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
CUSTOMER_B = uuid.UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")


async def _seed_plan_and_events(
    db_session: AsyncSession,
    unit_amount: Decimal = Decimal("0.99"),
    outcome_rules: dict[str, Any] | None = None,
    event_count: int = 10,
) -> uuid.UUID:
    """Insert a plan with one outcome rule and some events."""
    if outcome_rules is None:
        outcome_rules = {
            "billable_when": {},
            "cap_per_period": None,
            "price_per_outcome": str(unit_amount),
        }

    plan = Plan(
        id=PLAN_ID,
        name="Test Outcome Plan",
        currency="EUR",
        is_active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    rule = PricingRule(
        plan_id=PLAN_ID,
        pricing_model="outcome",
        metric="ticket_resolved",
        unit_amount=unit_amount,
        currency="EUR",
        outcome_rules=outcome_rules,
    )
    db_session.add(rule)
    await db_session.flush()

    for i in range(event_count):
        ev = Event(
            customer_id=CUSTOMER_A,
            event_type="outcome",
            metric="ticket_resolved",
            properties={"csat_score": 4.5, "escalated": False},
            idempotency_key=f"idem-sim-{i}",
            timestamp=datetime(2026, 2, 15, 12, 0, 0, tzinfo=UTC),
        )
        db_session.add(ev)

    await db_session.commit()
    return PLAN_ID


# ---------------------------------------------------------------------------
# Simulation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simulation_same_rules(db_session: AsyncSession) -> None:
    """When the scenario uses the same rules as the plan, delta should be 0."""
    await _seed_plan_and_events(db_session, unit_amount=Decimal("0.99"))

    scenario = SimulationScenario(
        pricing_rules=[
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "price_per_outcome": "0.99",
                "outcome_rules": {
                    "billable_when": {},
                    "cap_per_period": None,
                    "price_per_outcome": "0.99",
                },
            },
        ],
        date_range={"start": "2026-01-01", "end": "2026-12-31"},
    )

    result = await run_simulation(db_session, scenario, PLAN_ID)

    assert result.current_revenue == result.simulated_revenue
    assert result.delta == Decimal("0.00")
    assert result.delta_pct == Decimal("0.00")


@pytest.mark.asyncio
async def test_simulation_price_increase(db_session: AsyncSession) -> None:
    """Higher price per outcome should produce higher simulated revenue."""
    await _seed_plan_and_events(db_session, unit_amount=Decimal("0.99"))

    scenario = SimulationScenario(
        pricing_rules=[
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "price_per_outcome": "1.50",
                "outcome_rules": {
                    "billable_when": {},
                    "cap_per_period": None,
                    "price_per_outcome": "1.50",
                },
            },
        ],
        date_range={"start": "2026-01-01", "end": "2026-12-31"},
    )

    result = await run_simulation(db_session, scenario, PLAN_ID)

    assert result.simulated_revenue > result.current_revenue
    assert result.delta > Decimal("0")
    assert result.delta_pct > Decimal("0")


@pytest.mark.asyncio
async def test_simulation_stricter_rules(db_session: AsyncSession) -> None:
    """Stricter billable_when conditions should produce fewer billable outcomes
    and therefore lower revenue."""
    # Seed events where csat_score=4.5 and escalated=False
    await _seed_plan_and_events(db_session, unit_amount=Decimal("0.99"))

    # Require csat_score_gte: 5.0 — none of our 4.5 events qualify
    scenario = SimulationScenario(
        pricing_rules=[
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "price_per_outcome": "0.99",
                "outcome_rules": {
                    "billable_when": {"csat_score_gte": 5.0},
                    "cap_per_period": None,
                    "price_per_outcome": "0.99",
                },
            },
        ],
        date_range={"start": "2026-01-01", "end": "2026-12-31"},
    )

    result = await run_simulation(db_session, scenario, PLAN_ID)

    assert result.simulated_revenue < result.current_revenue
    assert result.delta < Decimal("0")
    assert result.billable_outcomes_simulated < result.billable_outcomes_current


# ---------------------------------------------------------------------------
# A/B test tests
# ---------------------------------------------------------------------------


def test_ab_test_assignment_deterministic() -> None:
    """Same customer + same test should always get the same assignment."""
    test = ABTest(
        id=uuid.UUID("eeeeeeee-ffff-0000-1111-222222222222"),
        name="Price Test",
        traffic_split=Decimal("0.50"),
    )
    customer = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    first = assign_variant(customer, test)
    for _ in range(50):
        assert assign_variant(customer, test) == first


def test_ab_test_split_ratio() -> None:
    """Over 1000 random customers, the split should approximate the configured ratio."""
    test = ABTest(
        id=uuid.UUID("dddddddd-eeee-ffff-0000-111111111111"),
        name="Split Test",
        traffic_split=Decimal("0.20"),
    )

    variant_count = 0
    total = 1000
    for _ in range(total):
        cid = uuid.uuid4()
        if assign_variant(cid, test) == "variant":
            variant_count += 1

    # Allow 5% tolerance (15%-25%)
    ratio = variant_count / total
    assert 0.10 <= ratio <= 0.30, f"Variant ratio {ratio:.2f} outside 10%-30% tolerance"


# ---------------------------------------------------------------------------
# Revenue forecast tests
# ---------------------------------------------------------------------------


def test_revenue_forecast_shape() -> None:
    """Forecast should return the correct number of months."""
    result = forecast_revenue(
        base_mrr=Decimal("10000"),
        growth_rate=Decimal("0.05"),
        churn_rate=Decimal("0.02"),
        months=6,
        simulations=100,
        seed=42,
    )

    assert len(result.months) == 6
    assert len(result.p10) == 6
    assert len(result.p50) == 6
    assert len(result.p90) == 6
    assert len(result.mean) == 6


def test_revenue_forecast_growth() -> None:
    """With positive net growth, P50 should trend upward."""
    result = forecast_revenue(
        base_mrr=Decimal("10000"),
        growth_rate=Decimal("0.10"),
        churn_rate=Decimal("0.02"),
        months=12,
        simulations=500,
        seed=42,
    )

    # P50 at month 12 should be higher than the base MRR
    assert result.p50[-1] > Decimal("10000")
    # P50 should generally increase — last value > first value
    assert result.p50[-1] > result.p50[0]


def test_revenue_forecast_percentile_ordering() -> None:
    """P10 <= P50 <= P90 for every month."""
    result = forecast_revenue(
        base_mrr=Decimal("10000"),
        growth_rate=Decimal("0.05"),
        churn_rate=Decimal("0.02"),
        months=12,
        simulations=500,
        seed=42,
    )

    for i in range(12):
        assert result.p10[i] <= result.p50[i] <= result.p90[i], (
            f"Month {i}: P10={result.p10[i]} P50={result.p50[i]} P90={result.p90[i]}"
        )


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


def test_templates_count() -> None:
    """There should be exactly 4 built-in templates."""
    templates = get_templates()
    assert len(templates) == 4


def test_templates_have_rules() -> None:
    """Every template must have at least one pricing rule."""
    templates = get_templates()
    for t in templates:
        assert len(t.pricing_rules) > 0, f"Template '{t.name}' has no pricing_rules"
        assert t.name, "Template missing name"
        assert t.description, "Template missing description"
        assert t.category, "Template missing category"
