"""Plan CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.api.middleware.auth import get_current_api_key
from rupiv.db import get_db
from rupiv.models.api_key import ApiKey
from rupiv.models.plan import Plan, PricingRule

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/plans", tags=["plans"])


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class PricingModelEnum(str, Enum):
    """Supported pricing models."""

    FLAT = "flat"
    USAGE = "usage"
    OUTCOME = "outcome"
    HYBRID = "hybrid"
    TIERED = "tiered"
    CREDIT = "credit"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class PricingRuleCreate(BaseModel):
    """A single pricing rule within a plan."""

    model: PricingModelEnum
    metric: str | None = None
    unit_price: Decimal = Field(default=Decimal("0"), decimal_places=4)
    flat_amount: Decimal = Field(default=Decimal("0"), decimal_places=4)
    tiers: list[dict[str, Decimal]] | None = None
    outcome_rules: dict[str, object] | None = None
    billing_interval: str | None = None


class PlanCreate(BaseModel):
    """Request body for creating a plan."""

    name: str
    description: str = ""
    currency: str = Field(default="EUR", max_length=3)
    billing_period: str = Field(default="monthly", description="monthly | yearly")
    pricing_rules: list[PricingRuleCreate] = Field(default_factory=list)


class PlanUpdate(BaseModel):
    """Request body for updating a plan."""

    name: str | None = None
    description: str | None = None
    currency: str | None = None
    billing_period: str | None = None
    pricing_rules: list[PricingRuleCreate] | None = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class PricingRuleResponse(BaseModel):
    """Pricing rule as returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model: PricingModelEnum
    metric: str | None = None
    unit_price: Decimal = Decimal("0")
    flat_amount: Decimal = Decimal("0")
    tiers: list[dict[str, Decimal]] | None = None
    outcome_rules: dict[str, object] | None = None


class PlanResponse(BaseModel):
    """Plan resource representation."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "b1c2d3e4-5f67-4a89-b012-3c4d5e6f7a8b",
                "name": "Support AI Pro",
                "description": "Outcome-based plan for AI support agents — per resolved ticket.",
                "currency": "EUR",
                "billing_period": "monthly",
                "pricing_rules": [
                    {
                        "id": "c3d4e5f6-7890-4abc-def0-123456789abc",
                        "model": "outcome",
                        "metric": "ticket_resolved",
                        "unit_price": "0.9900",
                        "flat_amount": "0.0000",
                        "tiers": None,
                        "outcome_rules": {
                            "billable_when": {
                                "csat_score_gte": 3.0,
                                "escalated": False,
                                "resolution_time_lt": 300,
                            },
                            "cap_per_period": 50000,
                        },
                    },
                ],
                "created_at": "2026-02-10T14:30:00Z",
                "updated_at": "2026-03-22T09:15:44Z",
            },
        },
    )

    id: uuid.UUID
    name: str
    description: str
    currency: str
    billing_period: str
    pricing_rules: list[PricingRuleResponse]
    created_at: datetime
    updated_at: datetime


class PlanListResponse(BaseModel):
    """Paginated list of plans."""

    model_config = ConfigDict(from_attributes=True)

    items: list[PlanResponse]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pricing_rule_to_response(rule: PricingRule) -> PricingRuleResponse:
    """Map an ORM PricingRule to its API response schema."""
    return PricingRuleResponse(
        id=rule.id,
        model=PricingModelEnum(
            rule.pricing_model.value
            if hasattr(rule.pricing_model, "value")
            else str(rule.pricing_model),
        ),
        metric=rule.metric,
        unit_price=rule.unit_amount if rule.unit_amount is not None else Decimal("0"),
        flat_amount=rule.flat_amount if rule.flat_amount is not None else Decimal("0"),
        tiers=rule.tiers,
        outcome_rules=rule.outcome_rules,
    )


def _plan_to_response(plan: Plan, billing_period: str = "monthly") -> PlanResponse:
    """Map an ORM Plan to its API response schema."""
    # Derive billing_period from the first pricing rule that has one,
    # falling back to the provided default.
    derived_period = billing_period
    for rule in plan.pricing_rules:
        if rule.billing_interval is not None:
            bi = rule.billing_interval
            derived_period = bi.value if hasattr(bi, "value") else str(bi)
            break

    return PlanResponse(
        id=plan.id,
        name=plan.name,
        description=plan.description or "",
        currency=plan.currency,
        billing_period=derived_period,
        pricing_rules=[_pricing_rule_to_response(r) for r in plan.pricing_rules],
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _build_pricing_rules(
    payload_rules: list[PricingRuleCreate],
    plan_id: uuid.UUID,
    billing_period: str,
) -> list[PricingRule]:
    """Convert API pricing rule payloads to ORM instances."""
    orm_rules: list[PricingRule] = []
    for pr in payload_rules:
        orm_rules.append(
            PricingRule(
                plan_id=plan_id,
                pricing_model=pr.model.value,
                metric=pr.metric,
                unit_amount=pr.unit_price,
                flat_amount=pr.flat_amount,
                tiers=pr.tiers,
                outcome_rules=pr.outcome_rules,
                billing_interval=pr.billing_interval or billing_period,
            ),
        )
    return orm_rules


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=PlanListResponse, summary="List plans")
async def list_plans(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> PlanListResponse:
    """Return a paginated list of plans."""
    logger.info("list_plans", limit=limit, offset=offset)

    # Total count
    count_stmt = select(func.count()).select_from(Plan)
    total: int = (await db.execute(count_stmt)).scalar_one()

    # Paginated rows with eager-loaded pricing_rules
    stmt = (
        select(Plan)
        .options(selectinload(Plan.pricing_rules))
        .order_by(Plan.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    plans: list[Plan] = list(result.scalars().all())

    return PlanListResponse(
        items=[_plan_to_response(p) for p in plans],
        total=total,
    )


@router.get("/{plan_id}", response_model=PlanResponse, summary="Get a plan")
async def get_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> PlanResponse:
    """Return a single plan by ID."""
    logger.info("get_plan", plan_id=str(plan_id))

    stmt = select(Plan).options(selectinload(Plan.pricing_rules)).where(Plan.id == plan_id)
    result = await db.execute(stmt)
    plan: Plan | None = result.scalar_one_or_none()

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    return _plan_to_response(plan)


@router.post(
    "",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a plan",
)
async def create_plan(
    payload: PlanCreate,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> PlanResponse:
    """Create a new billing plan."""
    logger.info("create_plan", name=payload.name)

    plan = Plan(
        name=payload.name,
        description=payload.description,
        currency=payload.currency,
    )
    db.add(plan)
    # Flush to generate plan.id before attaching pricing rules
    await db.flush()

    if payload.pricing_rules:
        rules = _build_pricing_rules(payload.pricing_rules, plan.id, payload.billing_period)
        for rule in rules:
            db.add(rule)
        await db.flush()

    # Refresh with relationships loaded
    stmt = select(Plan).options(selectinload(Plan.pricing_rules)).where(Plan.id == plan.id)
    result = await db.execute(stmt)
    plan = result.scalar_one()

    return _plan_to_response(plan, billing_period=payload.billing_period)


@router.patch("/{plan_id}", response_model=PlanResponse, summary="Update a plan")
async def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> PlanResponse:
    """Partially update a plan."""
    logger.info("update_plan", plan_id=str(plan_id))

    stmt = select(Plan).options(selectinload(Plan.pricing_rules)).where(Plan.id == plan_id)
    result = await db.execute(stmt)
    plan: Plan | None = result.scalar_one_or_none()

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    # Update scalar fields
    if payload.name is not None:
        plan.name = payload.name
    if payload.description is not None:
        plan.description = payload.description
    if payload.currency is not None:
        plan.currency = payload.currency

    # Replace pricing rules wholesale when provided
    if payload.pricing_rules is not None:
        # Remove existing rules (cascade handles DB deletes)
        plan.pricing_rules.clear()
        await db.flush()

        billing_period = payload.billing_period or "monthly"
        new_rules = _build_pricing_rules(payload.pricing_rules, plan.id, billing_period)
        for rule in new_rules:
            db.add(rule)
        await db.flush()

        # Re-fetch to get fresh relationship state
        stmt = select(Plan).options(selectinload(Plan.pricing_rules)).where(Plan.id == plan.id)
        result = await db.execute(stmt)
        plan = result.scalar_one()

    return _plan_to_response(plan, billing_period=payload.billing_period or "monthly")
