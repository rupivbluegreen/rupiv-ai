"""Alert management endpoints — list, acknowledge, resolve alerts and CRUD alert rules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.db import get_db
from rupiv.models.alert import Alert, AlertRule

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(tags=["alerts"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AlertResponse(BaseModel):
    """Alert resource."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_type: str
    severity: str
    customer_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    metric_name: str | None = None
    expected_value: Decimal | None = None
    actual_value: Decimal | None = None
    status: str
    resolved_at: datetime | None = None
    created_at: datetime


class AlertListResponse(BaseModel):
    """Paginated alert list."""

    items: list[AlertResponse]
    total: int


class AlertUpdate(BaseModel):
    """Request body for updating an alert status."""

    status: str = Field(pattern=r"^(acknowledged|resolved)$")


class AlertRuleResponse(BaseModel):
    """Alert rule resource."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    alert_type: str
    threshold_pct: Decimal
    lookback_periods: int
    is_active: bool
    created_at: datetime


class AlertRuleCreate(BaseModel):
    """Request body for creating an alert rule."""

    name: str = Field(min_length=1, max_length=255)
    alert_type: str = Field(
        pattern=r"^(mrr_drop|usage_spike|missed_invoice|validation_rate_drop)$",
    )
    threshold_pct: Decimal = Field(ge=0, le=100)
    lookback_periods: int = Field(default=3, ge=1, le=12)


class AlertRuleUpdate(BaseModel):
    """Request body for updating an alert rule."""

    name: str | None = None
    threshold_pct: Decimal | None = Field(default=None, ge=0, le=100)
    lookback_periods: int | None = Field(default=None, ge=1, le=12)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Alert endpoints
# ---------------------------------------------------------------------------


@router.get("/alerts", response_model=AlertListResponse, summary="List alerts")
async def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    alert_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """Return a paginated list of alerts."""
    stmt = select(Alert)
    count_stmt = select(func.count(Alert.id))

    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
        count_stmt = count_stmt.where(Alert.status == status_filter)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
        count_stmt = count_stmt.where(Alert.severity == severity)
    if alert_type:
        stmt = stmt.where(Alert.alert_type == alert_type)
        count_stmt = count_stmt.where(Alert.alert_type == alert_type)

    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = stmt.order_by(Alert.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    alerts = list(result.scalars().all())

    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
    )


@router.patch("/alerts/{alert_id}", response_model=AlertResponse, summary="Update alert status")
async def update_alert(
    alert_id: uuid.UUID,
    payload: AlertUpdate,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Acknowledge or resolve an alert."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert: Alert | None = result.scalar_one_or_none()

    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    values: dict[str, str | datetime] = {"status": payload.status}
    if payload.status == "resolved":
        values["resolved_at"] = datetime.now(UTC)

    await db.execute(update(Alert).where(Alert.id == alert_id).values(**values))
    await db.refresh(alert)

    return AlertResponse.model_validate(alert)


# ---------------------------------------------------------------------------
# Alert rule endpoints
# ---------------------------------------------------------------------------


@router.get("/alert-rules", response_model=list[AlertRuleResponse], summary="List alert rules")
async def list_alert_rules(
    db: AsyncSession = Depends(get_db),
) -> list[AlertRuleResponse]:
    """Return all alert rules."""
    result = await db.execute(select(AlertRule).order_by(AlertRule.created_at.desc()))
    rules = result.scalars().all()
    return [AlertRuleResponse.model_validate(r) for r in rules]


@router.post(
    "/alert-rules",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert rule",
)
async def create_alert_rule(
    payload: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> AlertRuleResponse:
    """Create a new alert rule."""
    rule = AlertRule(
        name=payload.name,
        alert_type=payload.alert_type,
        threshold_pct=payload.threshold_pct,
        lookback_periods=payload.lookback_periods,
        is_active=True,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return AlertRuleResponse.model_validate(rule)


@router.patch(
    "/alert-rules/{rule_id}",
    response_model=AlertRuleResponse,
    summary="Update an alert rule",
)
async def update_alert_rule(
    rule_id: uuid.UUID,
    payload: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> AlertRuleResponse:
    """Update an existing alert rule."""
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule: AlertRule | None = result.scalar_one_or_none()

    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    update_data = payload.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(update(AlertRule).where(AlertRule.id == rule_id).values(**update_data))
        await db.refresh(rule)

    return AlertRuleResponse.model_validate(rule)
