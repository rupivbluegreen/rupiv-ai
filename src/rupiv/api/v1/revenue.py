"""Revenue recognition endpoints — IFRS 15 schedules and journal entries."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.db import get_db
from rupiv.models.revenue_schedule import (
    EntryType,
    RevenueEntry,
    RevenueSchedule,
    ScheduleStatus,
)
from rupiv.models.subscription import Subscription
from rupiv.revenue_recognition.allocation import allocate_transaction_price
from rupiv.revenue_recognition.obligations import identify_obligations
from rupiv.revenue_recognition.schedules import generate_schedule

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/revenue", tags=["revenue"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ScheduleStatusEnum(str, Enum):
    """Revenue schedule status filter."""

    ACTIVE = "active"
    COMPLETED = "completed"
    VOIDED = "voided"


class RevenueEntryResponse(BaseModel):
    """Single period revenue entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    schedule_id: uuid.UUID
    period: str
    amount: Decimal = Field(decimal_places=4)
    entry_type: EntryType
    gl_debit: str
    gl_credit: str
    description: str
    created_at: datetime


class RevenueScheduleResponse(BaseModel):
    """Revenue schedule resource representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscription_id: uuid.UUID
    obligation_type: str
    recognition_method: str
    total_amount: Decimal = Field(decimal_places=4)
    recognized_amount: Decimal = Field(decimal_places=4)
    deferred_amount: Decimal = Field(decimal_places=4)
    currency: str
    status: ScheduleStatusEnum
    entries: list[RevenueEntryResponse] = []
    created_at: datetime
    updated_at: datetime


class RevenueScheduleListResponse(BaseModel):
    """Paginated list of revenue schedules."""

    model_config = ConfigDict(from_attributes=True)

    items: list[RevenueScheduleResponse]
    total: int


class GenerateScheduleRequest(BaseModel):
    """Request body for generating a revenue schedule."""

    subscription_id: uuid.UUID


class JournalEntryResponse(BaseModel):
    """GL journal entry for a period."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    schedule_id: uuid.UUID
    period: str
    amount: Decimal = Field(decimal_places=4)
    entry_type: EntryType
    gl_debit: str
    gl_credit: str
    description: str
    created_at: datetime


class JournalEntryListResponse(BaseModel):
    """List of journal entries for a period."""

    model_config = ConfigDict(from_attributes=True)

    items: list[JournalEntryResponse]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=RevenueScheduleListResponse, summary="List revenue schedules")
@router.get(
    "/schedules",
    response_model=RevenueScheduleListResponse,
    summary="List revenue schedules",
)
async def list_schedules(
    subscription_id: uuid.UUID | None = None,
    status: ScheduleStatusEnum | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> RevenueScheduleListResponse:
    """Return a paginated list of revenue schedules, optionally filtered."""
    logger.info(
        "list_revenue_schedules",
        subscription_id=str(subscription_id) if subscription_id else None,
        status=status,
        limit=limit,
        offset=offset,
    )

    base_stmt = select(RevenueSchedule)
    count_stmt = select(func.count(RevenueSchedule.id))

    if subscription_id is not None:
        base_stmt = base_stmt.where(RevenueSchedule.subscription_id == subscription_id)
        count_stmt = count_stmt.where(RevenueSchedule.subscription_id == subscription_id)

    if status is not None:
        base_stmt = base_stmt.where(RevenueSchedule.status == status.value)
        count_stmt = count_stmt.where(RevenueSchedule.status == status.value)

    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = (
        base_stmt.options(selectinload(RevenueSchedule.entries))
        .order_by(RevenueSchedule.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    schedules: list[RevenueSchedule] = list(result.scalars().all())

    return RevenueScheduleListResponse(
        items=[RevenueScheduleResponse.model_validate(s) for s in schedules],
        total=total,
    )


@router.get(
    "/schedules/{schedule_id}",
    response_model=RevenueScheduleResponse,
    summary="Get a revenue schedule with entries",
)
async def get_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RevenueScheduleResponse:
    """Return a single revenue schedule by ID, including all entries."""
    logger.info("get_revenue_schedule", schedule_id=str(schedule_id))

    stmt = (
        select(RevenueSchedule)
        .where(RevenueSchedule.id == schedule_id)
        .options(selectinload(RevenueSchedule.entries))
    )
    result = await db.execute(stmt)
    schedule: RevenueSchedule | None = result.scalar_one_or_none()

    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revenue schedule {schedule_id} not found",
        )

    return RevenueScheduleResponse.model_validate(schedule)


@router.post(
    "/schedules/generate",
    response_model=RevenueScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate revenue schedule for a subscription",
)
async def generate_schedule_endpoint(
    body: GenerateScheduleRequest,
    db: AsyncSession = Depends(get_db),
) -> RevenueScheduleResponse:
    """Generate an IFRS 15 revenue schedule for a subscription.

    Loads the subscription with its plan and pricing rules, identifies
    performance obligations, allocates the transaction price, generates
    per-period schedule entries, and persists the results.
    """
    logger.info(
        "generate_revenue_schedule",
        subscription_id=str(body.subscription_id),
    )

    # 1. Load subscription with plan and pricing rules
    stmt = (
        select(Subscription)
        .options(
            selectinload(Subscription.plan),
            selectinload(Subscription.customer),
        )
        .where(Subscription.id == body.subscription_id)
    )
    result = await db.execute(stmt)
    subscription: Subscription | None = result.scalar_one_or_none()

    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {body.subscription_id} not found",
        )

    plan = subscription.plan
    if not plan or not plan.pricing_rules:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Subscription plan has no pricing rules",
        )

    pricing_rules = plan.pricing_rules
    start_date = subscription.current_period_start.date()
    end_date = subscription.current_period_end.date()

    # 2. Identify performance obligations
    obligations = identify_obligations(
        subscription_id=subscription.id,
        plan_name=plan.name,
        pricing_rules=pricing_rules,
        start_date=start_date,
        end_date=end_date,
    )

    if not obligations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No performance obligations identified from pricing rules",
        )

    # 3. Allocate transaction price
    total_price = sum(ob.standalone_selling_price for ob in obligations)
    allocations = allocate_transaction_price(
        total_price=total_price,
        obligations=obligations,
    )

    # Build a lookup from obligation ID to allocation
    alloc_map = {a.obligation_id: a for a in allocations}

    # We will create one RevenueSchedule per obligation, then return the first.
    # For the API response, we combine into a single schedule if there is one
    # obligation, or create per-obligation schedules.
    created_schedules: list[RevenueSchedule] = []

    for obligation in obligations:
        allocation = alloc_map.get(obligation.id)
        allocated_amount = allocation.allocated_amount if allocation else Decimal("0")

        # 4. Generate schedule entries for this obligation
        schedule_entries = generate_schedule(
            obligation=obligation,
            total_allocated=allocated_amount,
            start=start_date,
            end=end_date,
        )

        # 5. Persist RevenueSchedule ORM object
        total_recognized = sum(e.recognized for e in schedule_entries)
        total_deferred = allocated_amount - total_recognized

        currency = getattr(plan, "currency", "EUR") or "EUR"

        db_schedule = RevenueSchedule(
            subscription_id=subscription.id,
            obligation_type=obligation.obligation_type,
            recognition_method=obligation.recognition_method,
            total_amount=allocated_amount,
            recognized_amount=total_recognized,
            deferred_amount=max(total_deferred, Decimal("0")),
            currency=currency,
            status=ScheduleStatus.ACTIVE,
        )
        db.add(db_schedule)
        await db.flush()

        # 6. Persist RevenueEntry ORM objects
        for entry in schedule_entries:
            db_entry = RevenueEntry(
                schedule_id=db_schedule.id,
                period=entry.period,
                amount=entry.recognized,
                entry_type=EntryType.RECOGNIZED,
                gl_debit=entry.gl_debit,
                gl_credit=entry.gl_credit,
                description=f"Revenue recognition — {entry.method} — {entry.period}",
            )
            db.add(db_entry)

            # If there is deferred revenue for this entry, persist a deferred entry
            if entry.deferred > 0:
                db_deferred = RevenueEntry(
                    schedule_id=db_schedule.id,
                    period=entry.period,
                    amount=entry.deferred,
                    entry_type=EntryType.DEFERRED,
                    gl_debit=entry.gl_debit,
                    gl_credit=entry.gl_credit,
                    description=f"Deferred revenue — {entry.method} — {entry.period}",
                )
                db.add(db_deferred)

        await db.flush()
        created_schedules.append(db_schedule)

        logger.info(
            "revenue_schedule_created",
            schedule_id=str(db_schedule.id),
            subscription_id=str(subscription.id),
            obligation_type=obligation.obligation_type,
            total_amount=str(allocated_amount),
            entry_count=len(schedule_entries),
        )

    # Reload the first schedule with entries for the response
    primary_schedule = created_schedules[0]
    reload_stmt = (
        select(RevenueSchedule)
        .where(RevenueSchedule.id == primary_schedule.id)
        .options(selectinload(RevenueSchedule.entries))
    )
    reload_result = await db.execute(reload_stmt)
    reloaded: RevenueSchedule = reload_result.scalar_one()

    return RevenueScheduleResponse.model_validate(reloaded)


@router.get(
    "/journal-entries",
    response_model=JournalEntryListResponse,
    summary="List GL journal entries for a period",
)
async def list_journal_entries(
    period: str = Query(
        ...,
        description="Period in YYYY-MM format",
        pattern=r"^\d{4}-\d{2}$",
    ),
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryListResponse:
    """Return GL journal entries (recognised revenue) for a given period."""
    logger.info("list_journal_entries", period=period, limit=limit, offset=offset)

    base_stmt = select(RevenueEntry).where(
        RevenueEntry.period == period,
        RevenueEntry.entry_type == EntryType.RECOGNIZED,
    )
    count_stmt = select(func.count(RevenueEntry.id)).where(
        RevenueEntry.period == period,
        RevenueEntry.entry_type == EntryType.RECOGNIZED,
    )

    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = base_stmt.order_by(RevenueEntry.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    entries: list[RevenueEntry] = list(result.scalars().all())

    return JournalEntryListResponse(
        items=[JournalEntryResponse.model_validate(e) for e in entries],
        total=total,
    )
