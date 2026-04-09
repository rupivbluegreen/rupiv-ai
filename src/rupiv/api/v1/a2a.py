"""Agent-to-Agent (A2A) payment intent endpoint."""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/a2a", tags=["a2a"])


class A2AIntentStatus(str, Enum):
    """Status of an A2A payment intent."""

    PENDING = "pending"
    APPROVED = "approved"
    SETTLED = "settled"
    REJECTED = "rejected"


class A2AIntentCreate(BaseModel):
    """Request body for creating an A2A payment intent."""

    from_agent_id: uuid.UUID = Field(..., description="Buyer agent identifier")
    to_agent_id: uuid.UUID = Field(..., description="Seller agent identifier")
    amount: Decimal = Field(..., gt=Decimal("0"), decimal_places=4)
    currency: str = Field(default="EUR", max_length=3)
    reason: str = Field(..., description="Purpose of the payment, e.g. 'data_enrichment'")
    idempotency_key: str


class A2AIntentResponse(BaseModel):
    """Response after creating an A2A payment intent."""

    intent_id: uuid.UUID
    status: A2AIntentStatus


@router.post(
    "/intent",
    response_model=A2AIntentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create an agent-to-agent payment intent",
)
async def create_a2a_intent(payload: A2AIntentCreate) -> A2AIntentResponse:
    """Create a new A2A payment intent for SEPA settlement.

    The compliance agent will verify GDPR/KYC constraints, reserve funds
    from the buyer ledger, and initiate SEPA credit transfer via Adyen.
    """
    intent_id = uuid.uuid4()
    logger.info(
        "a2a_intent_created",
        intent_id=str(intent_id),
        from_agent=str(payload.from_agent_id),
        to_agent=str(payload.to_agent_id),
        amount=str(payload.amount),
        currency=payload.currency,
        reason=payload.reason,
    )
    # TODO: Enqueue for compliance_agent + ledger reservation
    return A2AIntentResponse(intent_id=intent_id, status=A2AIntentStatus.PENDING)
