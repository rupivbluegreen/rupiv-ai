"""Customer self-service portal endpoints.

All endpoints require JWT authentication and are scoped to the
authenticated customer — customers can only see their own data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.api.middleware.auth import get_current_customer
from rupiv.db import get_db
from rupiv.models.customer import Customer
from rupiv.models.event import Event
from rupiv.models.invoice import Invoice
from rupiv.models.subscription import Subscription, SubscriptionStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/portal", tags=["portal"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PortalCustomerResponse(BaseModel):
    """Current customer profile."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    country_code: str
    currency: str
    is_business: bool
    vat_number: str | None = None


class PortalLineItem(BaseModel):
    """Invoice line item."""

    model_config = ConfigDict(from_attributes=True)

    description: str
    metric: str | None = None
    quantity: Decimal = Field(decimal_places=4)
    unit_amount: Decimal = Field(decimal_places=4)
    amount: Decimal = Field(decimal_places=4)


class PortalInvoiceResponse(BaseModel):
    """Invoice visible to the customer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    currency: str
    subtotal: Decimal = Field(decimal_places=4)
    tax_amount: Decimal = Field(decimal_places=4)
    total: Decimal = Field(decimal_places=4)
    line_items: list[PortalLineItem]
    period_start: datetime
    period_end: datetime
    due_date: date
    created_at: datetime


class PortalInvoiceListResponse(BaseModel):
    """Paginated invoice list."""

    items: list[PortalInvoiceResponse]
    total: int


class UsageMetricSummary(BaseModel):
    """Summary of usage for a single metric."""

    metric: str
    event_type: str
    count: int


class PortalUsageResponse(BaseModel):
    """Current-period usage summary."""

    customer_id: uuid.UUID
    period_start: datetime | None = None
    period_end: datetime | None = None
    metrics: list[UsageMetricSummary]


class PortalSubscriptionResponse(BaseModel):
    """Active subscription details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    canceled_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/me", response_model=PortalCustomerResponse, summary="Get my profile")
async def get_me(
    customer: Customer = Depends(get_current_customer),
) -> PortalCustomerResponse:
    """Return the authenticated customer's profile."""
    return PortalCustomerResponse.model_validate(customer)


@router.get(
    "/invoices",
    response_model=PortalInvoiceListResponse,
    summary="List my invoices",
)
async def list_my_invoices(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> PortalInvoiceListResponse:
    """Return the authenticated customer's invoices."""
    base = select(Invoice).where(Invoice.customer_id == customer.id)
    count_stmt = select(func.count(Invoice.id)).where(Invoice.customer_id == customer.id)

    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = (
        base.options(selectinload(Invoice.line_items))
        .order_by(Invoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    invoices = list(result.scalars().all())

    return PortalInvoiceListResponse(
        items=[PortalInvoiceResponse.model_validate(inv) for inv in invoices],
        total=total,
    )


@router.get(
    "/invoices/{invoice_id}",
    response_model=PortalInvoiceResponse,
    summary="Get one of my invoices",
)
async def get_my_invoice(
    invoice_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> PortalInvoiceResponse:
    """Return a single invoice, with ownership check."""
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.customer_id == customer.id)
        .options(selectinload(Invoice.line_items))
    )
    result = await db.execute(stmt)
    invoice: Invoice | None = result.scalar_one_or_none()

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    return PortalInvoiceResponse.model_validate(invoice)


@router.get("/invoices/{invoice_id}/pdf", summary="Download my invoice PDF")
async def get_my_invoice_pdf(
    invoice_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> FastAPIResponse:
    """Generate and return a PDF for the customer's invoice."""
    from rupiv.invoicing.pdf import generate_invoice_pdf

    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.customer_id == customer.id)
        .options(selectinload(Invoice.line_items))
    )
    result = await db.execute(stmt)
    invoice: Invoice | None = result.scalar_one_or_none()

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    pdf_bytes = generate_invoice_pdf(invoice)

    return FastAPIResponse(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice-{invoice.invoice_number}.pdf"',
        },
    )


@router.get("/usage", response_model=PortalUsageResponse, summary="My current usage")
async def get_my_usage(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> PortalUsageResponse:
    """Return usage summary from the current billing period.

    Falls back to PostgreSQL event counts (no ClickHouse required).
    """
    # Find the active subscription to determine the current period
    sub_result = await db.execute(
        select(Subscription)
        .where(
            Subscription.customer_id == customer.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .order_by(Subscription.created_at.desc())
        .limit(1),
    )
    subscription: Subscription | None = sub_result.scalar_one_or_none()

    period_start: datetime | None = None
    period_end: datetime | None = None

    event_count = func.count(Event.id).label("event_count")
    stmt = (
        select(
            Event.metric,
            Event.event_type,
            event_count,
        )
        .where(Event.customer_id == customer.id)
        .group_by(Event.metric, Event.event_type)
    )

    if subscription is not None:
        period_start = subscription.current_period_start
        period_end = subscription.current_period_end
        stmt = stmt.where(
            Event.timestamp >= period_start,
            Event.timestamp < period_end,
        )

    result = await db.execute(stmt)
    rows = result.all()

    metrics = [
        UsageMetricSummary(
            metric=str(row[0]),
            event_type=str(row[1]),
            count=int(row[2]),
        )
        for row in rows
    ]

    return PortalUsageResponse(
        customer_id=customer.id,
        period_start=period_start,
        period_end=period_end,
        metrics=metrics,
    )


@router.get(
    "/subscription",
    response_model=PortalSubscriptionResponse | None,
    summary="My active subscription",
)
async def get_my_subscription(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> PortalSubscriptionResponse | None:
    """Return the customer's active subscription, or null if none."""
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.customer_id == customer.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .order_by(Subscription.created_at.desc())
        .limit(1),
    )
    subscription: Subscription | None = result.scalar_one_or_none()

    if subscription is None:
        return None

    return PortalSubscriptionResponse.model_validate(subscription)
