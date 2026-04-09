"""Quote lifecycle endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.db import get_db
from rupiv.models.quote import Quote, QuoteLineItem, QuoteStatus
from rupiv.quoting.quote_acceptance import accept_quote, reject_quote
from rupiv.quoting.quote_builder import build_quote

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/quotes", tags=["quotes"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class QuoteCreate(BaseModel):
    """Request body for building a new quote."""

    customer_id: uuid.UUID
    plan_id: uuid.UUID
    discount_pct: Decimal = Field(default=Decimal("0"), decimal_places=2)
    term_months: int = 12
    overrides: dict[str, Decimal] | None = None


class QuoteReject(BaseModel):
    """Request body for rejecting a quote."""

    reason: str


class QuoteLineItemResponse(BaseModel):
    """Quote line item as returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    pricing_model: str
    metric: str | None = None
    unit_amount: Decimal = Decimal("0")
    estimated_quantity: Decimal = Decimal("0")
    estimated_amount: Decimal = Decimal("0")


class QuoteResponse(BaseModel):
    """Quote resource representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    discount_pct: Decimal
    estimated_monthly: Decimal
    estimated_total: Decimal
    currency: str
    term_months: int
    expires_at: datetime
    accepted_at: datetime | None = None
    notes: str | None = None
    line_items: list[QuoteLineItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class QuoteListResponse(BaseModel):
    """Paginated list of quotes."""

    items: list[QuoteResponse]
    total: int


class AcceptResponse(BaseModel):
    """Response after accepting a quote."""

    quote_id: uuid.UUID
    subscription_id: uuid.UUID
    contract_id: uuid.UUID


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=QuoteListResponse, summary="List quotes")
async def list_quotes(
    customer_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> QuoteListResponse:
    """Return a paginated list of quotes, with optional filters."""
    logger.info(
        "list_quotes",
        customer_id=str(customer_id) if customer_id else None,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )

    count_stmt = select(func.count(Quote.id))
    query_stmt = (
        select(Quote)
        .options(selectinload(Quote.line_items))
        .order_by(Quote.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if customer_id is not None:
        count_stmt = count_stmt.where(Quote.customer_id == customer_id)
        query_stmt = query_stmt.where(Quote.customer_id == customer_id)

    if status_filter is not None:
        count_stmt = count_stmt.where(Quote.status == status_filter)
        query_stmt = query_stmt.where(Quote.status == status_filter)

    total: int = (await session.execute(count_stmt)).scalar_one()

    result = await session.execute(query_stmt)
    rows: list[Quote] = list(result.scalars().all())

    return QuoteListResponse(
        items=[QuoteResponse.model_validate(row) for row in rows],
        total=total,
    )


@router.post(
    "",
    response_model=QuoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Build a new quote",
)
async def create_quote(
    payload: QuoteCreate,
    session: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Build a new quote from a plan's pricing rules."""
    logger.info(
        "create_quote",
        customer_id=str(payload.customer_id),
        plan_id=str(payload.plan_id),
    )

    try:
        quote = await build_quote(
            session,
            customer_id=payload.customer_id,
            plan_id=payload.plan_id,
            overrides=payload.overrides,
            discount_pct=payload.discount_pct,
            term_months=payload.term_months,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Re-fetch with line items eagerly loaded
    stmt = (
        select(Quote)
        .options(selectinload(Quote.line_items))
        .where(Quote.id == quote.id)
    )
    result = await session.execute(stmt)
    quote = result.scalar_one()

    return QuoteResponse.model_validate(quote)


@router.get("/{quote_id}", response_model=QuoteResponse, summary="Get a quote")
async def get_quote(
    quote_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Return a single quote with line items."""
    logger.info("get_quote", quote_id=str(quote_id))

    stmt = (
        select(Quote)
        .options(selectinload(Quote.line_items))
        .where(Quote.id == quote_id)
    )
    result = await session.execute(stmt)
    quote: Quote | None = result.scalar_one_or_none()

    if quote is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found",
        )

    return QuoteResponse.model_validate(quote)


@router.post(
    "/{quote_id}/send",
    response_model=QuoteResponse,
    summary="Mark a quote as sent",
)
async def send_quote(
    quote_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Mark a draft quote as sent to the customer."""
    logger.info("send_quote", quote_id=str(quote_id))

    stmt = (
        select(Quote)
        .options(selectinload(Quote.line_items))
        .where(Quote.id == quote_id)
    )
    result = await session.execute(stmt)
    quote: Quote | None = result.scalar_one_or_none()

    if quote is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found",
        )

    if quote.status != QuoteStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot send quote in status {quote.status.value}",
        )

    quote.status = QuoteStatus.SENT
    await session.flush()
    await session.refresh(quote)

    logger.info("quote_sent", quote_id=str(quote.id))

    return QuoteResponse.model_validate(quote)


@router.post(
    "/{quote_id}/accept",
    response_model=AcceptResponse,
    summary="Accept a quote",
)
async def accept_quote_endpoint(
    quote_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> AcceptResponse:
    """Accept a quote, creating a subscription and contract."""
    logger.info("accept_quote", quote_id=str(quote_id))

    try:
        subscription, contract = await accept_quote(session, quote_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return AcceptResponse(
        quote_id=quote_id,
        subscription_id=subscription.id,
        contract_id=contract.id,
    )


@router.post(
    "/{quote_id}/reject",
    response_model=QuoteResponse,
    summary="Reject a quote",
)
async def reject_quote_endpoint(
    quote_id: uuid.UUID,
    payload: QuoteReject,
    session: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Reject a quote with a reason."""
    logger.info("reject_quote", quote_id=str(quote_id), reason=payload.reason)

    try:
        quote = await reject_quote(session, quote_id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Re-fetch with line items
    stmt = (
        select(Quote)
        .options(selectinload(Quote.line_items))
        .where(Quote.id == quote.id)
    )
    result = await session.execute(stmt)
    quote = result.scalar_one()

    return QuoteResponse.model_validate(quote)
