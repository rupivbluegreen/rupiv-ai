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
        super().__init__(f"[{status_code}] {message}" + (f" (request_id={request_id})" if request_id else ""))


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
