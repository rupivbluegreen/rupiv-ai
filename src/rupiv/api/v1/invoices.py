"""Invoice endpoints — list and get."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.db import get_db
from rupiv.models.invoice import Invoice

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/invoices", tags=["invoices"])


class InvoiceStatus(str, Enum):
    """Invoice lifecycle status."""

    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class LineItem(BaseModel):
    """Single line item on an invoice."""

    model_config = ConfigDict(from_attributes=True)

    description: str
    metric: str | None = None
    quantity: Decimal = Field(decimal_places=4)
    unit_amount: Decimal = Field(decimal_places=4)
    amount: Decimal = Field(decimal_places=4)


class InvoiceResponse(BaseModel):
    """Invoice resource representation."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "d4e5f6a7-8901-4bcd-ef23-456789abcdef",
                "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                "status": "open",
                "currency": "EUR",
                "subtotal": "4950.0000",
                "tax_amount": "1039.5000",
                "total": "5989.5000",
                "line_items": [
                    {
                        "description": "Resolved support tickets (Mar 2026)",
                        "metric": "ticket_resolved",
                        "quantity": "5000.0000",
                        "unit_amount": "0.9900",
                        "amount": "4950.0000",
                    },
                ],
                "period_start": "2026-03-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
                "due_date": "2026-04-14",
                "created_at": "2026-04-01T02:00:00Z",
            },
        },
    )

    id: uuid.UUID
    customer_id: uuid.UUID
    status: InvoiceStatus
    currency: str
    subtotal: Decimal = Field(decimal_places=4)
    tax_amount: Decimal = Field(decimal_places=4)
    total: Decimal = Field(decimal_places=4)
    line_items: list[LineItem]
    period_start: datetime
    period_end: datetime
    due_date: date
    created_at: datetime


class InvoiceListResponse(BaseModel):
    """Paginated list of invoices."""

    model_config = ConfigDict(from_attributes=True)

    items: list[InvoiceResponse]
    total: int


@router.get("", response_model=InvoiceListResponse, summary="List invoices")
async def list_invoices(
    customer_id: uuid.UUID | None = None,
    status: InvoiceStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> InvoiceListResponse:
    """Return a paginated list of invoices, optionally filtered."""
    logger.info(
        "list_invoices",
        customer_id=str(customer_id) if customer_id else None,
        status=status,
        limit=limit,
        offset=offset,
    )

    # Build base query with filters
    base_stmt = select(Invoice)
    count_stmt = select(func.count(Invoice.id))

    if customer_id is not None:
        base_stmt = base_stmt.where(Invoice.customer_id == customer_id)
        count_stmt = count_stmt.where(Invoice.customer_id == customer_id)

    if status is not None:
        base_stmt = base_stmt.where(Invoice.status == status.value)
        count_stmt = count_stmt.where(Invoice.status == status.value)

    # Get total count
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Fetch paginated invoices with eagerly loaded line_items
    stmt = (
        base_stmt.options(selectinload(Invoice.line_items))
        .order_by(Invoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    invoices: list[Invoice] = list(result.scalars().all())

    return InvoiceListResponse(
        items=[InvoiceResponse.model_validate(inv) for inv in invoices],
        total=total,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse, summary="Get an invoice")
async def get_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """Return a single invoice by ID."""
    logger.info("get_invoice", invoice_id=str(invoice_id))

    stmt = (
        select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.line_items))
    )
    result = await db.execute(stmt)
    invoice: Invoice | None = result.scalar_one_or_none()

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found",
        )

    return InvoiceResponse.model_validate(invoice)
