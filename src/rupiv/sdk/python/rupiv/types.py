"""Pydantic models and exception types for the Rupiv SDK."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RupivError(Exception):
    """Raised when the Rupiv API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, request_id: str | None = None) -> None:
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        super().__init__(
            f"[{status_code}] {message}" + (f" (request_id={request_id})" if request_id else ""),
        )


class EventResponse(BaseModel):
    """Response returned after tracking an event or outcome."""

    id: str
    type: str
    metric: str
    customer_id: str
    properties: dict | None = None
    idempotency_key: str | None = None
    created_at: datetime


class PlanResponse(BaseModel):
    """A billing plan."""

    id: str
    name: str
    description: str | None = None
    created_at: datetime


class CustomerResponse(BaseModel):
    """A customer record."""

    id: str
    external_id: str
    name: str | None = None
    email: str | None = None
    plan: PlanResponse | None = None
    metadata: dict | None = None
    created_at: datetime


class InvoiceResponse(BaseModel):
    """An invoice record."""

    id: str
    customer_id: str
    status: str
    currency: str = "usd"
    amount_due: int = Field(description="Amount in smallest currency unit (e.g. cents)")
    amount_paid: int = 0
    line_items: list[dict] = Field(default_factory=list)
    period_start: datetime
    period_end: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------


class QuoteLineItemResponse(BaseModel):
    """A single line item on a quote."""

    id: str
    description: str
    quantity: int = 1
    unit_price: int = Field(description="Price in smallest currency unit")
    amount: int = Field(description="Total in smallest currency unit")
    metric: str | None = None


class QuoteResponse(BaseModel):
    """A quote record."""

    id: str
    customer_id: str
    plan_id: str
    status: str = "draft"
    currency: str = "eur"
    discount_pct: float = 0
    term_months: int = 12
    subtotal: int = Field(default=0, description="Subtotal in smallest currency unit")
    total: int = Field(default=0, description="Total after discount in smallest currency unit")
    line_items: list[QuoteLineItemResponse] = Field(default_factory=list)
    rejection_reason: str | None = None
    sent_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class AcceptResponse(BaseModel):
    """Response returned after accepting a quote."""

    quote_id: str
    subscription_id: str
    revenue_schedule_id: str
    status: str = "active"
    created_at: datetime


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------


class CreditBalanceResponse(BaseModel):
    """A customer's credit balance."""

    customer_id: str
    balance: int = Field(description="Available credits")
    currency: str = "eur"
    updated_at: datetime


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class EntityResponse(BaseModel):
    """A legal entity record (BV, GmbH, SAS, Ltd)."""

    id: str
    name: str
    legal_form: str
    country_code: str
    vat_id: str | None = None
    currency: str = "eur"
    parent_id: str | None = None
    metadata: dict | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Revenue Recognition
# ---------------------------------------------------------------------------


class RevenueScheduleResponse(BaseModel):
    """An IFRS 15 revenue recognition schedule."""

    id: str
    subscription_id: str
    total_amount: int = Field(description="Total contract value in smallest currency unit")
    recognized_amount: int = 0
    deferred_amount: int = 0
    currency: str = "eur"
    start_date: datetime
    end_date: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


class SimulationResult(BaseModel):
    """Result of a pricing simulation scenario."""

    plan_id: str
    scenario: dict
    projected_revenue: int = Field(description="Projected revenue in smallest currency unit")
    projected_customers: int = 0
    projected_events: int = 0
    currency: str = "eur"
    period_start: datetime
    period_end: datetime
