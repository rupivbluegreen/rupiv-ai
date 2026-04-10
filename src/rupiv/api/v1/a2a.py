"""Agent-to-Agent (A2A) payment intent endpoints.

Provides endpoints for creating A2A payment intents (which invoke the
LangGraph settlement agent), listing recent transactions, retrieving
transaction details, and querying account balances.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from rupiv.api.middleware.auth import get_current_api_key
from rupiv.models.api_key import ApiKey
from pydantic import BaseModel, Field

from rupiv.agents.a2a_agent import initiate_a2a_payment
from rupiv.billing import ledger

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/a2a", tags=["a2a"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class A2AIntentStatus(str, Enum):
    """Status of an A2A payment intent."""

    PENDING = "pending"
    APPROVED = "approved"
    SETTLED = "settled"
    REJECTED = "rejected"
    FAILED = "failed"


class A2AIntentCreate(BaseModel):
    """Request body for creating an A2A payment intent."""

    from_agent_id: uuid.UUID = Field(
        ...,
        description="Buyer agent identifier",
        example="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    )
    to_agent_id: uuid.UUID = Field(
        ...,
        description="Seller agent identifier",
        example="f6e5d4c3-b2a1-4098-7654-3210fedcba98",
    )
    amount: Decimal = Field(
        ...,
        gt=Decimal("0"),
        decimal_places=4,
        example="24.5000",
    )
    currency: str = Field(default="EUR", max_length=3, example="EUR")
    reason: str = Field(
        ...,
        description="Purpose of the payment, e.g. 'data_enrichment'",
        example="data_enrichment",
    )
    idempotency_key: str = Field(
        ..., example="a2a-20260409-nl-de-7f3a1b",
    )


class A2AIntentResponse(BaseModel):
    """Response after creating an A2A payment intent."""

    intent_id: str
    status: A2AIntentStatus
    settlement_status: str | None = None
    ledger_transaction_id: str | None = None
    psp_reference: str | None = None
    error: str | None = None


class LedgerEntryResponse(BaseModel):
    """Serialised ledger entry for API responses."""

    entry_id: str
    transaction_id: str
    account_id: str
    entry_type: str
    amount: str
    currency: str
    description: str
    status: str
    created_at: str


class BalanceResponse(BaseModel):
    """Account balance response."""

    account_id: str
    settled_balance: str
    available_balance: str
    currency: str


class TransactionDetailResponse(BaseModel):
    """Detail view of a ledger transaction (debit + credit pair)."""

    transaction_id: str
    entries: list[LedgerEntryResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry_to_response(entry: ledger.LedgerEntry) -> LedgerEntryResponse:
    """Convert an in-memory LedgerEntry to API response model."""
    return LedgerEntryResponse(
        entry_id=entry.entry_id,
        transaction_id=entry.transaction_id,
        account_id=entry.account_id,
        entry_type=entry.entry_type.value,
        amount=str(entry.amount),
        currency=entry.currency,
        description=entry.description,
        status=entry.status.value,
        created_at=entry.created_at.isoformat(),
    )


def _map_settlement_to_intent_status(settlement: str | None, error: str | None) -> A2AIntentStatus:
    """Map the agent graph settlement_status to an API-level intent status."""
    if error:
        return A2AIntentStatus.FAILED
    if settlement == "settled":
        return A2AIntentStatus.SETTLED
    if settlement == "pending":
        return A2AIntentStatus.PENDING
    if settlement == "failed":
        return A2AIntentStatus.FAILED
    return A2AIntentStatus.PENDING


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/intent",
    response_model=A2AIntentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create an agent-to-agent payment intent",
)
async def create_a2a_intent(
    payload: A2AIntentCreate,
    _api_key: ApiKey = Depends(get_current_api_key),
) -> A2AIntentResponse:
    """Create a new A2A payment intent and run the settlement agent graph.

    The compliance agent verifies policy rules, reserves funds from the
    buyer ledger, initiates SEPA credit transfer via Adyen, and settles
    the double-entry transaction on success.
    """
    logger.info(
        "a2a_intent_created",
        from_agent=str(payload.from_agent_id),
        to_agent=str(payload.to_agent_id),
        amount=str(payload.amount),
        currency=payload.currency,
        reason=payload.reason,
    )

    result = await initiate_a2a_payment(
        buyer_agent_id=str(payload.from_agent_id),
        seller_agent_id=str(payload.to_agent_id),
        amount=str(payload.amount),
        currency=payload.currency,
        reason=payload.reason,
    )

    intent_status = _map_settlement_to_intent_status(
        result.get("settlement_status"),
        result.get("error"),
    )

    return A2AIntentResponse(
        intent_id=result.get("intent_id", ""),
        status=intent_status,
        settlement_status=result.get("settlement_status"),
        ledger_transaction_id=result.get("ledger_transaction_id"),
        psp_reference=result.get("psp_reference"),
        error=result.get("error"),
    )


@router.get(
    "/intents",
    response_model=list[LedgerEntryResponse],
    summary="List recent A2A transactions",
)
async def list_a2a_intents(
    limit: int = 50,
    _api_key: ApiKey = Depends(get_current_api_key),
) -> list[LedgerEntryResponse]:
    """List recent A2A ledger entries (most recent first).

    Returns the raw double-entry ledger entries. Each A2A transaction
    produces a debit + credit pair sharing the same ``transaction_id``.
    """
    entries = await ledger.get_recent_entries(limit=limit)
    return [_entry_to_response(e) for e in entries]


@router.get(
    "/intents/{transaction_id}",
    response_model=TransactionDetailResponse,
    summary="Get A2A transaction details",
)
async def get_a2a_intent(
    transaction_id: str,
    _api_key: ApiKey = Depends(get_current_api_key),
) -> TransactionDetailResponse:
    """Retrieve the debit + credit entries for a specific transaction."""
    entries = await ledger.get_entries_by_transaction(transaction_id)
    if not entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} not found",
        )

    return TransactionDetailResponse(
        transaction_id=transaction_id,
        entries=[_entry_to_response(e) for e in entries],
    )


@router.get(
    "/balance/{account_id}",
    response_model=BalanceResponse,
    summary="Get account balance",
)
async def get_account_balance(
    account_id: str,
    _api_key: ApiKey = Depends(get_current_api_key),
) -> BalanceResponse:
    """Return the settled and available balance for an agent account.

    - ``settled_balance``: Sum of settled credits minus settled debits.
    - ``available_balance``: Settled balance minus pending debits (funds
      that are reserved but not yet settled).
    """
    settled = await ledger.get_balance(account_id)
    available = await ledger.get_available_balance(account_id)

    return BalanceResponse(
        account_id=account_id,
        settled_balance=str(settled),
        available_balance=str(available),
        currency="EUR",
    )
