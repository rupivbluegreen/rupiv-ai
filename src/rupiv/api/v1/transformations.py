"""Transformation rule endpoints — CRUD and test/preview."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.db import get_db
from rupiv.models.transformation_rule import TransformationRule
from rupiv.transformations.engine import transform_event

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/transformations", tags=["transformations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TransformationStep(BaseModel):
    """A single transformation step."""

    type: str = Field(description="filter | rename | map | set")
    field: str | None = None
    source: str | None = None
    target: str | None = None
    operator: str | None = None
    value: Any = None
    expression: str | None = None


class TransformationRuleResponse(BaseModel):
    """Transformation rule resource."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    source_metric: str
    target_metric: str
    is_active: bool
    priority: int
    steps: list[dict[str, Any]]
    created_at: datetime


class TransformationRuleCreate(BaseModel):
    """Request body for creating a transformation rule."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    source_metric: str = Field(min_length=1)
    target_metric: str = Field(min_length=1)
    priority: int = Field(default=100, ge=0)
    steps: list[dict[str, Any]] = Field(min_length=1)


class TransformationRuleUpdate(BaseModel):
    """Request body for updating a transformation rule."""

    name: str | None = None
    description: str | None = None
    source_metric: str | None = None
    target_metric: str | None = None
    priority: int | None = None
    steps: list[dict[str, Any]] | None = None
    is_active: bool | None = None


class TestTransformationRequest(BaseModel):
    """Request body for testing a transformation."""

    event: dict[str, Any] = Field(description="Sample event to transform")
    steps: list[dict[str, Any]] = Field(description="Steps to apply")


class TestTransformationResponse(BaseModel):
    """Result of a transformation test."""

    input: dict[str, Any]
    output: dict[str, Any] | None
    dropped: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[TransformationRuleResponse])
async def list_rules(
    db: AsyncSession = Depends(get_db),
) -> list[TransformationRuleResponse]:
    """List all transformation rules, ordered by priority."""
    result = await db.execute(select(TransformationRule).order_by(TransformationRule.priority))
    rules = result.scalars().all()
    return [TransformationRuleResponse.model_validate(r) for r in rules]


@router.post(
    "",
    response_model=TransformationRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule(
    payload: TransformationRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> TransformationRuleResponse:
    """Create a new transformation rule."""
    rule = TransformationRule(
        name=payload.name,
        description=payload.description,
        source_metric=payload.source_metric,
        target_metric=payload.target_metric,
        priority=payload.priority,
        steps=payload.steps,
        is_active=True,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return TransformationRuleResponse.model_validate(rule)


@router.put("/{rule_id}", response_model=TransformationRuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    payload: TransformationRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> TransformationRuleResponse:
    """Update an existing transformation rule."""
    result = await db.execute(
        select(TransformationRule).where(TransformationRule.id == rule_id),
    )
    rule: TransformationRule | None = result.scalar_one_or_none()

    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
    await db.flush()
    await db.refresh(rule)

    return TransformationRuleResponse.model_validate(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a transformation rule (set is_active=False)."""
    result = await db.execute(
        select(TransformationRule).where(TransformationRule.id == rule_id),
    )
    rule: TransformationRule | None = result.scalar_one_or_none()

    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    await db.execute(
        update(TransformationRule)
        .where(TransformationRule.id == rule_id)
        .values(is_active=False),
    )


@router.post("/test", response_model=TestTransformationResponse)
async def test_transformation(
    payload: TestTransformationRequest,
) -> TestTransformationResponse:
    """Dry-run a transformation on a sample event.

    Returns the transformed event or indicates it was dropped by a filter.
    """
    output = transform_event(payload.event, payload.steps)
    return TestTransformationResponse(
        input=payload.event,
        output=output,
        dropped=output is None,
    )
