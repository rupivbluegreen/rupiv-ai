"""Self-serve onboarding endpoints — signup, billing, status, upgrade."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.api.middleware.auth import generate_api_key
from rupiv.db import get_db
from rupiv.models.api_key import ApiKey
from rupiv.models.customer import Customer
from rupiv.models.plan import BillingInterval, Plan, PricingModel, PricingRule
from rupiv.models.subscription import Subscription, SubscriptionStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FREE_PLAN_NAME = "Free"
FREE_PLAN_EVENT_LIMIT = 10_000
FREE_PLAN_CUSTOMER_LIMIT = 3


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    """All-in-one signup payload."""

    company_name: str
    email: str
    country_code: str = "NL"
    is_business: bool = True
    vat_number: str | None = None


class SignupResponse(BaseModel):
    """Returned once after successful signup."""

    customer_id: uuid.UUID
    subscription_id: uuid.UUID
    api_key: str
    dashboard_url: str


class SetupBillingRequest(BaseModel):
    """Start a payment-method checkout session."""

    customer_id: uuid.UUID
    payment_provider: str = "mollie"  # or "stripe"
    return_url: str


class SetupBillingResponse(BaseModel):
    """Redirect URL for the payment-method checkout."""

    redirect_url: str


class OnboardingStatus(BaseModel):
    """Onboarding progress checklist."""

    has_customer: bool
    has_subscription: bool
    has_api_key: bool
    has_payment_method: bool
    has_first_event: bool
    completion_pct: int


class UpgradeRequest(BaseModel):
    """Upgrade from free tier to a paid plan."""

    customer_id: uuid.UUID
    plan_id: uuid.UUID


class UpgradeResponse(BaseModel):
    """Result of a plan upgrade."""

    old_subscription_id: uuid.UUID
    new_subscription_id: uuid.UUID
    plan_id: uuid.UUID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_or_create_free_plan(session: AsyncSession) -> Plan:
    """Return the Free plan, creating it if it does not exist."""
    result = await session.execute(
        select(Plan).where(Plan.name == FREE_PLAN_NAME, Plan.is_active.is_(True)),
    )
    plan: Plan | None = result.scalar_one_or_none()

    if plan is not None:
        return plan

    logger.info("onboarding_creating_free_plan")
    plan = Plan(
        name=FREE_PLAN_NAME,
        description=(
            f"Free tier: up to {FREE_PLAN_EVENT_LIMIT:,} events/month, "
            f"{FREE_PLAN_CUSTOMER_LIMIT} customers"
        ),
        is_active=True,
        currency="EUR",
    )
    session.add(plan)
    await session.flush()

    # Add a flat pricing rule at EUR 0.00
    rule = PricingRule(
        plan_id=plan.id,
        pricing_model=PricingModel.FLAT,
        flat_amount=Decimal("0.0000"),
        currency="EUR",
        billing_interval=BillingInterval.MONTHLY,
        outcome_rules={
            "event_limit": FREE_PLAN_EVENT_LIMIT,
            "customer_limit": FREE_PLAN_CUSTOMER_LIMIT,
        },
    )
    session.add(rule)
    await session.flush()
    await session.refresh(plan)

    return plan


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="All-in-one self-serve signup",
)
async def signup(
    payload: SignupRequest,
    session: AsyncSession = Depends(get_db),
) -> SignupResponse:
    """Create a customer, free-tier subscription, and API key in one call.

    The API key is returned **once** and cannot be retrieved again.
    """
    logger.info(
        "onboarding_signup",
        company_name=payload.company_name,
        email=payload.email,
    )

    # 1. Check for duplicate email
    existing = await session.execute(select(Customer).where(Customer.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A customer with this email already exists",
        )

    # 2. Create Customer
    external_id = f"onb_{uuid.uuid4().hex[:12]}"
    customer = Customer(
        name=payload.company_name,
        email=payload.email,
        external_id=external_id,
        country_code=payload.country_code,
        currency="EUR",
        is_business=payload.is_business,
        billing_email=payload.email,
        vat_number=payload.vat_number,
    )
    session.add(customer)
    await session.flush()

    # 3. Find or create the Free plan, then create subscription
    free_plan = await _get_or_create_free_plan(session)

    now = datetime.now(UTC)
    subscription = Subscription(
        customer_id=customer.id,
        plan_id=free_plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    session.add(subscription)
    await session.flush()

    # 4. Generate API key (shown once)
    full_key, key_hash = generate_api_key()
    api_key = ApiKey(
        customer_id=customer.id,
        key_prefix=full_key[:8],
        key_hash=key_hash,
        name="Default (onboarding)",
        is_active=True,
    )
    session.add(api_key)
    await session.flush()

    logger.info(
        "onboarding_signup_complete",
        customer_id=str(customer.id),
        subscription_id=str(subscription.id),
    )

    return SignupResponse(
        customer_id=customer.id,
        subscription_id=subscription.id,
        api_key=full_key,
        dashboard_url=f"/overview?customer_id={customer.id}",
    )


@router.post(
    "/setup-billing",
    response_model=SetupBillingResponse,
    summary="Create a checkout session to add a payment method",
)
async def setup_billing(
    payload: SetupBillingRequest,
    session: AsyncSession = Depends(get_db),
) -> SetupBillingResponse:
    """Start a Mollie or Stripe checkout session for adding a payment method."""
    logger.info(
        "onboarding_setup_billing",
        customer_id=str(payload.customer_id),
        provider=payload.payment_provider,
    )

    # Verify customer exists
    result = await session.execute(select(Customer).where(Customer.id == payload.customer_id))
    customer: Customer | None = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {payload.customer_id} not found",
        )

    # Build a checkout redirect URL per provider.
    # In production this calls the Mollie / Stripe SDK to create a real
    # checkout session.  For now we return a placeholder URL.
    if payload.payment_provider == "mollie":
        redirect_url = (
            f"https://checkout.mollie.com/setup"
            f"?customer={customer.id}"
            f"&return_url={payload.return_url}"
        )
    elif payload.payment_provider == "stripe":
        redirect_url = (
            f"https://checkout.stripe.com/setup"
            f"?customer={customer.id}"
            f"&return_url={payload.return_url}"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported payment provider: {payload.payment_provider}",
        )

    return SetupBillingResponse(redirect_url=redirect_url)


@router.get(
    "/status/{customer_id}",
    response_model=OnboardingStatus,
    summary="Check onboarding progress",
)
async def onboarding_status(
    customer_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> OnboardingStatus:
    """Return a checklist of completed onboarding steps."""
    logger.info("onboarding_status", customer_id=str(customer_id))

    # Customer
    cust_result = await session.execute(select(Customer).where(Customer.id == customer_id))
    has_customer = cust_result.scalar_one_or_none() is not None

    # Subscription
    sub_result = await session.execute(
        select(Subscription).where(
            Subscription.customer_id == customer_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        ),
    )
    has_subscription = sub_result.scalar_one_or_none() is not None

    # API key
    key_result = await session.execute(
        select(ApiKey).where(
            ApiKey.customer_id == customer_id,
            ApiKey.is_active.is_(True),
        ),
    )
    has_api_key = key_result.scalar_one_or_none() is not None

    # Payment method — check metadata for payment_method_id
    # (set by webhook after Mollie/Stripe setup completes)
    has_payment_method = False
    if has_customer:
        cust = (
            await session.execute(select(Customer).where(Customer.id == customer_id))
        ).scalar_one()
        if cust.metadata_ and cust.metadata_.get("payment_method_id"):
            has_payment_method = True

    # First event — check if any event exists for this customer
    has_first_event = False
    try:
        from rupiv.models.event import Event  # noqa: F811

        evt_result = await session.execute(
            select(Event).where(Event.customer_id == customer_id).limit(1),
        )
        has_first_event = evt_result.scalar_one_or_none() is not None
    except Exception:
        # Event model/table may not be available in all environments
        logger.debug("onboarding_event_check_failed", customer_id=str(customer_id))

    # Completion percentage
    steps = [has_customer, has_subscription, has_api_key, has_payment_method, has_first_event]
    completion_pct = int((sum(steps) / len(steps)) * 100)

    return OnboardingStatus(
        has_customer=has_customer,
        has_subscription=has_subscription,
        has_api_key=has_api_key,
        has_payment_method=has_payment_method,
        has_first_event=has_first_event,
        completion_pct=completion_pct,
    )


@router.post(
    "/upgrade",
    response_model=UpgradeResponse,
    summary="Upgrade from free tier to a paid plan",
)
async def upgrade(
    payload: UpgradeRequest,
    session: AsyncSession = Depends(get_db),
) -> UpgradeResponse:
    """Cancel the free subscription and create a new one on the selected plan."""
    logger.info(
        "onboarding_upgrade",
        customer_id=str(payload.customer_id),
        plan_id=str(payload.plan_id),
    )

    # Verify customer
    cust_result = await session.execute(select(Customer).where(Customer.id == payload.customer_id))
    if cust_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {payload.customer_id} not found",
        )

    # Verify target plan
    plan_result = await session.execute(
        select(Plan).where(Plan.id == payload.plan_id, Plan.is_active.is_(True)),
    )
    if plan_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {payload.plan_id} not found or inactive",
        )

    # Find current active subscription (should be the free tier)
    sub_result = await session.execute(
        select(Subscription).where(
            Subscription.customer_id == payload.customer_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        ),
    )
    old_sub: Subscription | None = sub_result.scalar_one_or_none()
    if old_sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found to upgrade",
        )

    # Cancel old subscription
    now = datetime.now(UTC)
    old_sub.status = SubscriptionStatus.CANCELED
    old_sub.canceled_at = now
    await session.flush()

    # Create new subscription
    new_sub = Subscription(
        customer_id=payload.customer_id,
        plan_id=payload.plan_id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    session.add(new_sub)
    await session.flush()

    logger.info(
        "onboarding_upgrade_complete",
        old_subscription_id=str(old_sub.id),
        new_subscription_id=str(new_sub.id),
        plan_id=str(payload.plan_id),
    )

    return UpgradeResponse(
        old_subscription_id=old_sub.id,
        new_subscription_id=new_sub.id,
        plan_id=payload.plan_id,
    )
