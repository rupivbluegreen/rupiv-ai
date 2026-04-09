"""Tests for the quoting module — Quote-to-Cash lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.contract import Contract, ContractRenewalType, ContractStatus
from rupiv.models.customer import Customer
from rupiv.models.plan import BillingInterval, Plan, PricingModel, PricingRule
from rupiv.models.quote import QuoteStatus
from rupiv.models.subscription import Subscription, SubscriptionStatus
from rupiv.quoting.contract import (
    calculate_early_termination_fee,
    check_renewal_due,
    get_active_contract,
)
from rupiv.quoting.quote_acceptance import (
    accept_quote,
    expire_stale_quotes,
    reject_quote,
)
from rupiv.quoting.quote_builder import build_quote

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — create prerequisite data within each test
# ---------------------------------------------------------------------------


async def _create_customer(session: AsyncSession) -> Customer:
    """Insert and return a sample customer."""
    customer = Customer(
        id=uuid.uuid4(),
        name="Test Corp",
        email="billing@test.example.com",
        external_id=f"ext-{uuid.uuid4().hex[:8]}",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    session.add(customer)
    await session.flush()
    return customer


async def _create_plan_flat(session: AsyncSession) -> Plan:
    """Insert a plan with a single flat pricing rule."""
    plan = Plan(
        id=uuid.uuid4(),
        name="Starter Flat",
        description="Fixed monthly fee",
        is_active=True,
        currency="EUR",
    )
    session.add(plan)
    await session.flush()

    rule = PricingRule(
        plan_id=plan.id,
        pricing_model=PricingModel.FLAT,
        flat_amount=Decimal("99.0000"),
        currency="EUR",
        billing_interval=BillingInterval.MONTHLY,
    )
    session.add(rule)
    await session.flush()
    await session.refresh(plan)
    return plan


async def _create_plan_outcome(session: AsyncSession) -> Plan:
    """Insert a plan with a flat base + outcome pricing rule."""
    plan = Plan(
        id=uuid.uuid4(),
        name="Outcome Growth",
        description="Pay per resolved ticket",
        is_active=True,
        currency="EUR",
    )
    session.add(plan)
    await session.flush()

    flat_rule = PricingRule(
        plan_id=plan.id,
        pricing_model=PricingModel.FLAT,
        flat_amount=Decimal("49.0000"),
        currency="EUR",
        billing_interval=BillingInterval.MONTHLY,
    )
    outcome_rule = PricingRule(
        plan_id=plan.id,
        pricing_model=PricingModel.OUTCOME,
        metric="ticket_resolved",
        unit_amount=Decimal("0.9900"),
        currency="EUR",
        billing_interval=BillingInterval.MONTHLY,
    )
    session.add(flat_rule)
    session.add(outcome_rule)
    await session.flush()
    await session.refresh(plan)
    return plan


# ---------------------------------------------------------------------------
# Tests — Quote Builder
# ---------------------------------------------------------------------------


async def test_build_quote(db_session: AsyncSession) -> None:
    """Build a quote from a plan with flat + outcome rules, verify line items."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_outcome(db_session)

    quote = await build_quote(
        db_session,
        customer_id=customer.id,
        plan_id=plan.id,
        overrides={"ticket_resolved": Decimal("1000")},
        term_months=12,
    )

    assert quote.status == QuoteStatus.DRAFT
    assert quote.customer_id == customer.id
    assert quote.plan_id == plan.id
    assert quote.term_months == 12
    assert quote.currency == "EUR"
    assert len(quote.line_items) == 2

    # Find line items by pricing model
    flat_item = next(li for li in quote.line_items if li.pricing_model == "flat")
    outcome_item = next(li for li in quote.line_items if li.pricing_model == "outcome")

    assert Decimal(str(flat_item.estimated_amount)) == Decimal("49.0000")
    assert Decimal(str(outcome_item.unit_amount)) == Decimal("0.9900")
    assert Decimal(str(outcome_item.estimated_quantity)) == Decimal("1000")
    assert Decimal(str(outcome_item.estimated_amount)) == Decimal("990.0000")

    # Monthly = 49 + 990 = 1039; Total = 1039 * 12 = 12468
    assert Decimal(str(quote.estimated_monthly)) == Decimal("1039.0000")
    assert Decimal(str(quote.estimated_total)) == Decimal("12468.0000")

    # Expiry is ~30 days from now (SQLite strips timezone info, so compare naive)
    now_naive = datetime.now(tz=UTC).replace(tzinfo=None)
    expires = (
        quote.expires_at.replace(tzinfo=None) if quote.expires_at.tzinfo else quote.expires_at
    )
    assert expires > now_naive - timedelta(minutes=1)
    assert expires <= now_naive + timedelta(days=31)


async def test_build_quote_with_discount(db_session: AsyncSession) -> None:
    """A 20% discount is applied correctly to the quote totals."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_flat(db_session)

    quote = await build_quote(
        db_session,
        customer_id=customer.id,
        plan_id=plan.id,
        discount_pct=Decimal("20"),
        term_months=12,
    )

    # Flat fee = 99, with 20% discount => 79.20/mo, 950.40 total
    assert Decimal(str(quote.estimated_monthly)) == Decimal("79.2000")
    assert Decimal(str(quote.estimated_total)) == Decimal("950.4000")
    assert Decimal(str(quote.discount_pct)) == Decimal("20.00")


# ---------------------------------------------------------------------------
# Tests — Quote Acceptance
# ---------------------------------------------------------------------------


async def test_accept_quote(db_session: AsyncSession) -> None:
    """Accepting a quote creates a subscription and contract."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_flat(db_session)

    quote = await build_quote(
        db_session,
        customer_id=customer.id,
        plan_id=plan.id,
        term_months=12,
    )

    subscription, contract = await accept_quote(db_session, quote.id)

    # Refresh quote to get updated status
    await db_session.refresh(quote)

    assert quote.status == QuoteStatus.ACCEPTED
    assert quote.accepted_at is not None

    assert subscription.customer_id == customer.id
    assert subscription.plan_id == plan.id
    assert subscription.status == SubscriptionStatus.ACTIVE

    assert contract.quote_id == quote.id
    assert contract.subscription_id == subscription.id
    assert contract.term_months == 12
    assert contract.renewal_type == ContractRenewalType.AUTO
    assert contract.status == ContractStatus.ACTIVE


async def test_accept_expired_quote(db_session: AsyncSession) -> None:
    """Attempting to accept an expired quote raises ValueError."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_flat(db_session)

    quote = await build_quote(
        db_session,
        customer_id=customer.id,
        plan_id=plan.id,
        expires_in_days=0,  # Expires immediately
    )

    # Manually set expires_at to the past
    quote.expires_at = datetime.now(tz=UTC) - timedelta(hours=1)
    await db_session.flush()

    with pytest.raises(ValueError, match="expired"):
        await accept_quote(db_session, quote.id)


async def test_reject_quote(db_session: AsyncSession) -> None:
    """Rejecting a quote sets status to rejected with a reason."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_flat(db_session)

    quote = await build_quote(
        db_session,
        customer_id=customer.id,
        plan_id=plan.id,
    )

    rejected = await reject_quote(db_session, quote.id, reason="Too expensive")

    assert rejected.status == QuoteStatus.REJECTED
    assert rejected.notes == "Too expensive"


async def test_expire_stale_quotes(db_session: AsyncSession) -> None:
    """Stale quotes past their expiry are marked as expired."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_flat(db_session)

    # Create a quote that is already expired
    quote = await build_quote(
        db_session,
        customer_id=customer.id,
        plan_id=plan.id,
    )
    quote.expires_at = datetime.now(tz=UTC) - timedelta(days=1)
    await db_session.flush()

    # Create a fresh quote that should NOT be expired
    fresh_quote = await build_quote(
        db_session,
        customer_id=customer.id,
        plan_id=plan.id,
        expires_in_days=30,
    )

    count = await expire_stale_quotes(db_session)

    assert count == 1

    await db_session.refresh(quote)
    await db_session.refresh(fresh_quote)

    assert quote.status == QuoteStatus.EXPIRED
    assert fresh_quote.status == QuoteStatus.DRAFT


# ---------------------------------------------------------------------------
# Tests — Contract Management
# ---------------------------------------------------------------------------


async def test_contract_renewal_check(db_session: AsyncSession) -> None:
    """A contract within 30 days of end_date with AUTO renewal is due."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_flat(db_session)

    # Create subscription directly
    now = datetime.now(tz=UTC)
    subscription = Subscription(
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db_session.add(subscription)
    await db_session.flush()

    # Contract ending in 15 days — should be due
    contract_due = Contract(
        subscription_id=subscription.id,
        start_date=date.today() - timedelta(days=350),
        end_date=date.today() + timedelta(days=15),
        term_months=12,
        renewal_type=ContractRenewalType.AUTO,
        status=ContractStatus.ACTIVE,
    )
    db_session.add(contract_due)
    await db_session.flush()

    assert check_renewal_due(contract_due) is True

    # Contract ending in 60 days — should NOT be due
    contract_not_due = Contract(
        subscription_id=subscription.id,
        start_date=date.today() - timedelta(days=305),
        end_date=date.today() + timedelta(days=60),
        term_months=12,
        renewal_type=ContractRenewalType.AUTO,
        status=ContractStatus.ACTIVE,
    )
    db_session.add(contract_not_due)
    await db_session.flush()

    assert check_renewal_due(contract_not_due) is False

    # Contract with MANUAL renewal — should NOT be due even if within 30 days
    contract_manual = Contract(
        subscription_id=subscription.id,
        start_date=date.today() - timedelta(days=350),
        end_date=date.today() + timedelta(days=10),
        term_months=12,
        renewal_type=ContractRenewalType.MANUAL,
        status=ContractStatus.ACTIVE,
    )
    db_session.add(contract_manual)
    await db_session.flush()

    assert check_renewal_due(contract_manual) is False


async def test_early_termination_fee(db_session: AsyncSession) -> None:
    """Early termination fee is calculated correctly for mid-term cancel."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_flat(db_session)

    now = datetime.now(tz=UTC)
    subscription = Subscription(
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db_session.add(subscription)
    await db_session.flush()

    contract = Contract(
        subscription_id=subscription.id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=365),
        term_months=12,
        renewal_type=ContractRenewalType.AUTO,
        early_termination_pct=Decimal("50"),
        status=ContractStatus.ACTIVE,
    )
    db_session.add(contract)
    await db_session.flush()

    # Cancel 6 months in (approximately 180 days remaining)
    cancellation_date = date.today() + timedelta(days=185)
    monthly_value = Decimal("99.0000")

    fee = calculate_early_termination_fee(contract, cancellation_date, monthly_value=monthly_value)

    # Remaining ~ 180 days = 6 months, fee = 6 * 99 * 0.50 = 297
    remaining_days = (contract.end_date - cancellation_date).days
    expected_months = (Decimal(str(remaining_days)) / Decimal("30")).quantize(
        Decimal("1"), rounding="ROUND_UP",
    )
    expected_fee = expected_months * monthly_value * Decimal("0.50")

    assert fee == expected_fee
    assert fee > Decimal("0")

    # Cancel after end date — no fee
    fee_after = calculate_early_termination_fee(
        contract,
        contract.end_date + timedelta(days=1),
        monthly_value=monthly_value,
    )
    assert fee_after == Decimal("0")


async def test_get_active_contract(db_session: AsyncSession) -> None:
    """get_active_contract returns the active contract, or None."""
    customer = await _create_customer(db_session)
    plan = await _create_plan_flat(db_session)

    now = datetime.now(tz=UTC)
    subscription = Subscription(
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db_session.add(subscription)
    await db_session.flush()

    # No contract yet
    result = await get_active_contract(db_session, subscription.id)
    assert result is None

    # Add an active contract
    contract = Contract(
        subscription_id=subscription.id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=365),
        term_months=12,
        renewal_type=ContractRenewalType.AUTO,
        status=ContractStatus.ACTIVE,
    )
    db_session.add(contract)
    await db_session.flush()

    result = await get_active_contract(db_session, subscription.id)
    assert result is not None
    assert result.id == contract.id

    # Terminate the contract — should return None
    contract.status = ContractStatus.TERMINATED
    await db_session.flush()

    result = await get_active_contract(db_session, subscription.id)
    assert result is None
