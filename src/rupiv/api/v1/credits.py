"""Credit management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.credits import (
    get_or_create_balance,
    get_transactions,
    purchase_credits,
)
from rupiv.db import get_db
from rupiv.models.credit import TransactionType

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/credits", tags=["credits"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreditBalanceResponse(BaseModel):
    """Current credit balance for a customer."""

    model_config = ConfigDict(from_attributes=True)

    customer_id: uuid.UUID
    balance: Decimal
    currency: str


class CreditTransactionResponse(BaseModel):
    """A single credit transaction."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    transaction_type: TransactionType
    amount: Decimal
    description: str
    reference_type: str | None = None
    reference_id: uuid.UUID | None = None
    created_at: datetime


class CreditTransactionListResponse(BaseModel):
    """Paginated list of credit transactions."""

    items: list[CreditTransactionResponse]
    total: int


class PurchaseCreditsRequest(BaseModel):
    """Request body for purchasing credits."""

    amount: Decimal = Field(..., gt=0, description="Number of credits to purchase")
    description: str = Field(default="Credit purchase")
    invoice_id: uuid.UUID | None = None


class AdjustCreditsRequest(BaseModel):
    """Request body for manual credit adjustment (admin only)."""

    amount: Decimal = Field(..., description="Positive to add, negative to deduct")
    description: str = Field(..., description="Reason for adjustment")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{customer_id}/balance",
    response_model=CreditBalanceResponse,
    summary="Get credit balance",
)
async def get_credit_balance(
    customer_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> CreditBalanceResponse:
    """Return the current credit balance for a customer."""
    logger.info("credits.get_balance", customer_id=str(customer_id))

    balance_obj = await get_or_create_balance(session, customer_id)
    return CreditBalanceResponse(
        customer_id=balance_obj.customer_id,
        balance=Decimal(str(balance_obj.balance)),
        currency=balance_obj.currency,
    )


@router.get(
    "/{customer_id}/transactions",
    response_model=CreditTransactionListResponse,
    summary="List credit transactions",
)
async def list_credit_transactions(
    customer_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> CreditTransactionListResponse:
    """Return paginated credit transactions for a customer, newest first."""
    logger.info(
        "credits.list_transactions",
        customer_id=str(customer_id),
        limit=limit,
        offset=offset,
    )

    txns = await get_transactions(session, customer_id, limit=limit, offset=offset)
    items = [CreditTransactionResponse.model_validate(t) for t in txns]

    # For total count, fetch without limit
    all_txns = await get_transactions(session, customer_id, limit=0)
    total = len(all_txns)

    return CreditTransactionListResponse(items=items, total=total)


@router.post(
    "/{customer_id}/purchase",
    response_model=CreditTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Purchase credits",
)
async def purchase_credits_endpoint(
    customer_id: uuid.UUID,
    payload: PurchaseCreditsRequest,
    session: AsyncSession = Depends(get_db),
) -> CreditTransactionResponse:
    """Purchase credits for a customer. Creates a credit transaction."""
    logger.info(
        "credits.purchase",
        customer_id=str(customer_id),
        amount=str(payload.amount),
    )

    txn = await purchase_credits(
        session,
        customer_id,
        amount=payload.amount,
        description=payload.description,
        invoice_id=payload.invoice_id,
    )
    return CreditTransactionResponse.model_validate(txn)


@router.post(
    "/{customer_id}/adjust",
    response_model=CreditTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adjust credits (admin)",
)
async def adjust_credits_endpoint(
    customer_id: uuid.UUID,
    payload: AdjustCreditsRequest,
    session: AsyncSession = Depends(get_db),
) -> CreditTransactionResponse:
    """Manually adjust a customer's credit balance (admin only).

    Positive amount adds credits, negative amount deducts.
    """
    logger.info(
        "credits.adjust",
        customer_id=str(customer_id),
        amount=str(payload.amount),
    )

    balance = await get_or_create_balance(session, customer_id)

    from rupiv.models.credit import CreditTransaction

    current = Decimal(str(balance.balance))
    new_balance = current + payload.amount

    if new_balance < Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Adjustment would result in negative balance: {new_balance}",
        )

    balance.balance = new_balance

    txn = CreditTransaction(
        customer_id=customer_id,
        credit_balance_id=balance.id,
        transaction_type=TransactionType.ADJUSTMENT,
        amount=payload.amount,
        description=payload.description,
    )
    session.add(txn)
    await session.flush()

    return CreditTransactionResponse.model_validate(txn)
