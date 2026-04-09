"""Tests for payment routing, MRR/ARR, churn, outcome metrics, and cohorts."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.analytics.cohort import calculate_cohorts
from rupiv.analytics.mrr_arr import calculate_arr, calculate_churn_rate, calculate_mrr
from rupiv.analytics.outcome_metrics import calculate_outcome_metrics
from rupiv.analytics.routing_optimizer import PSPRoute, find_cheapest_route
from rupiv.models.customer import Customer
from rupiv.models.event import Event, EventType, OutcomeStatus
from rupiv.models.plan import BillingInterval, Plan, PricingModel, PricingRule
from rupiv.models.subscription import Subscription, SubscriptionStatus

# ---------------------------------------------------------------------------
# Routing optimizer tests
# ---------------------------------------------------------------------------


class TestCheapestRouteIdeal:
    """iDEAL: Adyen should be cheaper than Mollie."""

    def test_cheapest_route_ideal(self) -> None:
        route = find_cheapest_route(
            amount=Decimal("50.00"),
            currency="EUR",
            country_code="NL",
            payment_method="ideal",
        )

        assert isinstance(route, PSPRoute)
        assert route.psp == "adyen"
        assert route.method == "ideal"
        # Adyen iDEAL = 0.22, Mollie iDEAL = 0.29
        assert route.estimated_fee == Decimal("0.2200")
        assert "adyen" in route.reason.lower() or "cheapest" in route.reason.lower()


class TestCheapestRouteCard:
    """Card payments: verify rate + fixed fee interaction."""

    def test_cheapest_route_card_small(self) -> None:
        """Small card payment — Adyen should be cheaper (lower fixed + lower rate)."""
        route = find_cheapest_route(
            amount=Decimal("10.00"),
            currency="EUR",
            country_code="FR",
            payment_method="card",
        )

        assert route.psp == "adyen"
        assert route.method == "card"
        # Adyen: 0.20 + 10 * 2.2% = 0.20 + 0.22 = 0.42
        # Mollie: 0.25 + 10 * 2.9% = 0.25 + 0.29 = 0.54
        assert route.estimated_fee == Decimal("0.4200")

    def test_cheapest_route_card_large(self) -> None:
        """Large card payment — Adyen still cheaper due to lower rate."""
        route = find_cheapest_route(
            amount=Decimal("1000.00"),
            currency="EUR",
            country_code="FR",
            payment_method="card",
        )

        assert route.psp == "adyen"
        # Adyen: 0.20 + 1000 * 2.2% = 0.20 + 22 = 22.20
        # Mollie: 0.25 + 1000 * 2.9% = 0.25 + 29 = 29.25
        assert route.estimated_fee == Decimal("22.2000")


class TestCheapestRouteSepa:
    """SEPA DD comparison — Adyen cheaper than Mollie."""

    def test_cheapest_route_sepa(self) -> None:
        route = find_cheapest_route(
            amount=Decimal("100.00"),
            currency="EUR",
            country_code="DE",
            payment_method="sepa_dd",
        )

        assert route.psp == "adyen"
        assert route.method == "sepa_dd"
        # Adyen SEPA DD = 0.30, Mollie SEPA DD = 0.35
        assert route.estimated_fee == Decimal("0.3000")


class TestCheapestRouteBancontact:
    """Bancontact only available on Mollie."""

    def test_bancontact_mollie_only(self) -> None:
        route = find_cheapest_route(
            amount=Decimal("25.00"),
            currency="EUR",
            country_code="BE",
            payment_method="bancontact",
        )

        assert route.psp == "mollie"
        assert route.method == "bancontact"
        assert route.estimated_fee == Decimal("0.2900")
        assert "only" in route.reason.lower()


class TestCheapestRouteCountryDefault:
    """When no method given, country preferred method is used."""

    def test_nl_defaults_to_ideal(self) -> None:
        route = find_cheapest_route(
            amount=Decimal("50.00"),
            currency="EUR",
            country_code="NL",
        )
        assert route.method == "ideal"

    def test_de_defaults_to_sepa(self) -> None:
        route = find_cheapest_route(
            amount=Decimal("50.00"),
            currency="EUR",
            country_code="DE",
        )
        assert route.method == "sepa_dd"


# ---------------------------------------------------------------------------
# MRR / ARR tests
# ---------------------------------------------------------------------------


def _make_plan(
    plan_id: uuid.UUID,
    flat_amount: Decimal,
    interval: BillingInterval = BillingInterval.MONTHLY,
) -> Plan:
    """Create a Plan with a single flat pricing rule."""
    plan = Plan(
        id=plan_id,
        name="Test Plan",
        currency="EUR",
    )
    rule = PricingRule(
        id=uuid.uuid4(),
        plan_id=plan_id,
        pricing_model=PricingModel.FLAT,
        flat_amount=flat_amount,
        billing_interval=interval,
        currency="EUR",
    )
    plan.pricing_rules = [rule]
    return plan


def _make_subscription(
    customer_id: uuid.UUID,
    plan_id: uuid.UUID,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    created_at: datetime | None = None,
    canceled_at: datetime | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> Subscription:
    """Create a Subscription instance."""
    now = datetime.now(UTC)
    return Subscription(
        id=uuid.uuid4(),
        customer_id=customer_id,
        plan_id=plan_id,
        status=status,
        current_period_start=period_start or now.replace(day=1),
        current_period_end=period_end or now.replace(month=now.month % 12 + 1, day=1)
        if period_end is None
        else period_end,
        canceled_at=canceled_at,
        created_at=created_at or now,
    )


@pytest.mark.asyncio
async def test_mrr_calculation(db_session: AsyncSession) -> None:
    """Create subscriptions, calculate MRR — should sum flat amounts."""
    customer_id = uuid.uuid4()
    customer = Customer(
        id=customer_id,
        name="MRR Test Co",
        email="mrr@test.example.com",
        external_id="ext-mrr-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer)

    plan_id = uuid.uuid4()
    plan = _make_plan(plan_id, Decimal("99.0000"))
    db_session.add(plan)
    await db_session.flush()

    sub = Subscription(
        id=uuid.uuid4(),
        customer_id=customer_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime(2026, 4, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 5, 1, tzinfo=UTC),
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    db_session.add(sub)

    # Second customer with different plan
    customer2_id = uuid.uuid4()
    customer2 = Customer(
        id=customer2_id,
        name="MRR Test Co 2",
        email="mrr2@test.example.com",
        external_id="ext-mrr-002",
        country_code="DE",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer2)

    plan2_id = uuid.uuid4()
    plan2 = _make_plan(plan2_id, Decimal("149.0000"))
    db_session.add(plan2)
    await db_session.flush()

    sub2 = Subscription(
        id=uuid.uuid4(),
        customer_id=customer2_id,
        plan_id=plan2_id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime(2026, 4, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 5, 1, tzinfo=UTC),
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    db_session.add(sub2)
    await db_session.commit()

    result = await calculate_mrr(db_session, date(2026, 4, 15))

    assert result.total_mrr == Decimal("248.0000")
    assert result.customer_count == 2
    assert result.period == "2026-04"
    assert result.new_mrr == Decimal("248.0000")  # both created this month


@pytest.mark.asyncio
async def test_arr_is_mrr_times_12(db_session: AsyncSession) -> None:
    """ARR should be exactly MRR * 12."""
    customer_id = uuid.uuid4()
    customer = Customer(
        id=customer_id,
        name="ARR Test Co",
        email="arr@test.example.com",
        external_id="ext-arr-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer)

    plan_id = uuid.uuid4()
    plan = _make_plan(plan_id, Decimal("100.0000"))
    db_session.add(plan)
    await db_session.flush()

    sub = Subscription(
        id=uuid.uuid4(),
        customer_id=customer_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime(2026, 4, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 5, 1, tzinfo=UTC),
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    db_session.add(sub)
    await db_session.commit()

    as_of = date(2026, 4, 15)
    mrr = await calculate_mrr(db_session, as_of)
    arr = await calculate_arr(db_session, as_of)

    assert arr == mrr.total_mrr * Decimal("12")
    assert arr == Decimal("1200.0000")


@pytest.mark.asyncio
async def test_churn_rate(db_session: AsyncSession) -> None:
    """Cancel a subscription, verify churn rate."""
    customer_id = uuid.uuid4()
    customer = Customer(
        id=customer_id,
        name="Churn Test Co",
        email="churn@test.example.com",
        external_id="ext-churn-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer)

    plan_id = uuid.uuid4()
    plan = _make_plan(plan_id, Decimal("50.0000"))
    db_session.add(plan)
    await db_session.flush()

    # 2 subs created before the period — one active, one canceled during period
    sub_active = Subscription(
        id=uuid.uuid4(),
        customer_id=customer_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime(2026, 3, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 4, 1, tzinfo=UTC),
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    sub_churned = Subscription(
        id=uuid.uuid4(),
        customer_id=customer_id,
        plan_id=plan_id,
        status=SubscriptionStatus.CANCELED,
        current_period_start=datetime(2026, 3, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 4, 1, tzinfo=UTC),
        canceled_at=datetime(2026, 3, 15, tzinfo=UTC),
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    db_session.add_all([sub_active, sub_churned])
    await db_session.commit()

    rate = await calculate_churn_rate(
        db_session,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 4, 1),
    )

    # 1 churned out of 2 active at start = 0.5
    assert rate == Decimal("0.5000")


# ---------------------------------------------------------------------------
# Outcome metrics tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outcome_metrics(db_session: AsyncSession) -> None:
    """Mix of validated/rejected outcomes, verify rates."""
    customer_id = uuid.uuid4()
    customer = Customer(
        id=customer_id,
        name="Outcome Test Co",
        email="outcome@test.example.com",
        external_id="ext-outcome-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer)
    await db_session.flush()

    # Create outcome events: 3 validated, 1 rejected, 1 pending = 5 total
    events = [
        Event(
            id=uuid.uuid4(),
            customer_id=customer_id,
            event_type=EventType.OUTCOME,
            metric="ticket_resolved",
            idempotency_key=f"idem-outcome-{i}",
            outcome_status=status,
            timestamp=datetime(2026, 4, 10, tzinfo=UTC),
            properties={"resolution_time": 30},
        )
        for i, status in enumerate(
            [
                OutcomeStatus.VALIDATED,
                OutcomeStatus.VALIDATED,
                OutcomeStatus.VALIDATED,
                OutcomeStatus.REJECTED,
                OutcomeStatus.PENDING,
            ],
        )
    ]
    db_session.add_all(events)
    await db_session.commit()

    results = await calculate_outcome_metrics(
        db_session,
        customer_id=customer_id,
        metric="ticket_resolved",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 5, 1),
    )

    assert len(results) == 1
    m = results[0]
    assert m.metric == "ticket_resolved"
    assert m.total_events == 5
    assert m.validated == 3
    assert m.rejected == 1
    assert m.pending == 1
    # success_rate = 3/5 * 100 = 60.00
    assert m.success_rate == Decimal("60.00")


# ---------------------------------------------------------------------------
# Cohort retention tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cohort_retention(db_session: AsyncSession) -> None:
    """3-month cohort, verify retention rates decline."""
    plan_id = uuid.uuid4()
    plan = _make_plan(plan_id, Decimal("100.0000"))
    db_session.add(plan)
    await db_session.flush()

    # Create 3 customers in Jan 2026 cohort
    customer_ids: list[uuid.UUID] = []
    for i in range(3):
        cid = uuid.uuid4()
        customer_ids.append(cid)
        customer = Customer(
            id=cid,
            name=f"Cohort Customer {i}",
            email=f"cohort{i}@test.example.com",
            external_id=f"ext-cohort-{i}",
            country_code="NL",
            is_business=True,
            currency="EUR",
            created_at=datetime(2026, 1, 5, tzinfo=UTC),
        )
        db_session.add(customer)

    await db_session.flush()

    # All 3 active in Jan, 2 in Feb, 1 in Mar
    # Customer 0: active all 3 months
    db_session.add(
        Subscription(
            id=uuid.uuid4(),
            customer_id=customer_ids[0],
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=datetime(2026, 1, 1, tzinfo=UTC),
            current_period_end=datetime(2026, 4, 1, tzinfo=UTC),
            created_at=datetime(2026, 1, 5, tzinfo=UTC),
        ),
    )

    # Customer 1: active Jan-Feb (period covers Jan 1 - Feb 28)
    db_session.add(
        Subscription(
            id=uuid.uuid4(),
            customer_id=customer_ids[1],
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=datetime(2026, 1, 1, tzinfo=UTC),
            current_period_end=datetime(2026, 2, 28, tzinfo=UTC),
            created_at=datetime(2026, 1, 5, tzinfo=UTC),
        ),
    )

    # Customer 2: active Jan only (period covers Jan 1 - Jan 31)
    db_session.add(
        Subscription(
            id=uuid.uuid4(),
            customer_id=customer_ids[2],
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=datetime(2026, 1, 1, tzinfo=UTC),
            current_period_end=datetime(2026, 1, 31, tzinfo=UTC),
            created_at=datetime(2026, 1, 5, tzinfo=UTC),
        ),
    )

    await db_session.commit()

    entries = await calculate_cohorts(db_session, start_month="2026-01", num_months=3)

    # Filter to just the Jan 2026 cohort
    jan_entries = [e for e in entries if e.cohort_month == "2026-01"]
    assert len(jan_entries) == 3  # offsets 0, 1, 2

    # Month 0 (Jan): 3/3 = 100%
    m0 = next(e for e in jan_entries if e.month_offset == 0)
    assert m0.customers == 3
    assert m0.retained == 3
    assert m0.retention_rate == Decimal("100.00")

    # Month 1 (Feb): 2/3
    m1 = next(e for e in jan_entries if e.month_offset == 1)
    assert m1.customers == 3
    assert m1.retained == 2
    assert m1.retention_rate == Decimal("66.67")

    # Month 2 (Mar): 1/3
    m2 = next(e for e in jan_entries if e.month_offset == 2)
    assert m2.customers == 3
    assert m2.retained == 1
    assert m2.retention_rate == Decimal("33.33")
