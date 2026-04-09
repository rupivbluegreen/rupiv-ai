"""Synchronous and asynchronous HTTP clients for the Rupiv API."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from .types import (
    AcceptResponse,
    CreditBalanceResponse,
    CustomerResponse,
    EntityResponse,
    EventResponse,
    InvoiceResponse,
    QuoteResponse,
    RupivError,
    SimulationResult,
)

_DEFAULT_BASE_URL = "https://api.rupiv.ai"
_DEFAULT_TIMEOUT = 30.0


def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "rupiv-python/0.1.0",
    }


def _handle_response(response: httpx.Response) -> dict[str, Any]:
    """Raise RupivError on non-2xx; otherwise return parsed JSON."""
    if not response.is_success:
        request_id = response.headers.get("x-request-id")
        try:
            body = response.json()
            message = body.get("error", {}).get("message", response.text)
        except Exception:
            message = response.text
        raise RupivError(
            status_code=response.status_code,
            message=message,
            request_id=request_id,
        )
    return response.json()


def _event_payload(
    metric: str,
    customer_id: str,
    event_type: str,
    properties: dict | None,
    idempotency_key: str | None,
) -> dict[str, Any]:
    return {
        "metric": metric,
        "customer_id": customer_id,
        "type": event_type,
        "properties": properties or {},
        "idempotency_key": idempotency_key or str(uuid.uuid4()),
    }


class Client:
    """Synchronous Rupiv API client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base_url,
            headers=_build_headers(api_key),
            timeout=timeout,
        )

    # -- Events ----------------------------------------------------------------

    def track_event(
        self,
        metric: str,
        customer_id: str,
        properties: dict | None = None,
        idempotency_key: str | None = None,
    ) -> EventResponse:
        """Track a usage event (e.g. API call, message sent)."""
        payload = _event_payload(metric, customer_id, "usage", properties, idempotency_key)
        data = _handle_response(self._http.post("/v1/events", json=payload))
        return EventResponse.model_validate(data)

    def track_outcome(
        self,
        metric: str,
        customer_id: str,
        properties: dict | None = None,
        idempotency_key: str | None = None,
    ) -> EventResponse:
        """Track a business outcome (e.g. ticket resolved, lead generated)."""
        payload = _event_payload(metric, customer_id, "outcome", properties, idempotency_key)
        data = _handle_response(self._http.post("/v1/events", json=payload))
        return EventResponse.model_validate(data)

    # -- Customers -------------------------------------------------------------

    def get_customer(self, customer_id: str) -> CustomerResponse:
        """Fetch a customer by ID."""
        data = _handle_response(self._http.get(f"/v1/customers/{customer_id}"))
        return CustomerResponse.model_validate(data)

    # -- Invoices --------------------------------------------------------------

    def list_invoices(self, customer_id: str | None = None) -> list[InvoiceResponse]:
        """List invoices, optionally filtered by customer."""
        params: dict[str, str] = {}
        if customer_id is not None:
            params["customer_id"] = customer_id
        data = _handle_response(self._http.get("/v1/invoices", params=params))
        return [InvoiceResponse.model_validate(inv) for inv in data]

    # -- Quotes ----------------------------------------------------------------

    def create_quote(
        self,
        customer_id: str,
        plan_id: str,
        discount_pct: float = 0,
        term_months: int = 12,
        idempotency_key: str | None = None,
    ) -> QuoteResponse:
        """Create a new quote for a customer."""
        payload: dict[str, Any] = {
            "customer_id": customer_id,
            "plan_id": plan_id,
            "discount_pct": discount_pct,
            "term_months": term_months,
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
        }
        data = _handle_response(self._http.post("/v1/quotes", json=payload))
        return QuoteResponse.model_validate(data)

    def get_quote(self, quote_id: str) -> QuoteResponse:
        """Fetch a single quote by ID."""
        data = _handle_response(self._http.get(f"/v1/quotes/{quote_id}"))
        return QuoteResponse.model_validate(data)

    def list_quotes(
        self,
        customer_id: str | None = None,
        status: str | None = None,
    ) -> list[QuoteResponse]:
        """List quotes, optionally filtered by customer and/or status."""
        params: dict[str, str] = {}
        if customer_id is not None:
            params["customer_id"] = customer_id
        if status is not None:
            params["status"] = status
        data = _handle_response(self._http.get("/v1/quotes", params=params))
        return [QuoteResponse.model_validate(q) for q in data]

    def send_quote(self, quote_id: str) -> QuoteResponse:
        """Send a draft quote to the customer."""
        data = _handle_response(self._http.post(f"/v1/quotes/{quote_id}/send"))
        return QuoteResponse.model_validate(data)

    def accept_quote(self, quote_id: str) -> AcceptResponse:
        """Accept a quote, creating a subscription and revenue schedule."""
        data = _handle_response(self._http.post(f"/v1/quotes/{quote_id}/accept"))
        return AcceptResponse.model_validate(data)

    def reject_quote(self, quote_id: str, reason: str) -> QuoteResponse:
        """Reject a quote with a reason."""
        data = _handle_response(
            self._http.post(f"/v1/quotes/{quote_id}/reject", json={"reason": reason}),
        )
        return QuoteResponse.model_validate(data)

    # -- Credits ---------------------------------------------------------------

    def get_credits(self, customer_id: str) -> CreditBalanceResponse:
        """Fetch a customer's credit balance."""
        data = _handle_response(self._http.get(f"/v1/credits/{customer_id}/balance"))
        return CreditBalanceResponse.model_validate(data)

    def purchase_credits(
        self,
        customer_id: str,
        amount: int,
        idempotency_key: str | None = None,
    ) -> CreditBalanceResponse:
        """Purchase credits for a customer."""
        payload: dict[str, Any] = {
            "customer_id": customer_id,
            "amount": amount,
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
        }
        data = _handle_response(self._http.post("/v1/credits/purchase", json=payload))
        return CreditBalanceResponse.model_validate(data)

    # -- Entities --------------------------------------------------------------

    def list_entities(self) -> list[EntityResponse]:
        """List all legal entities."""
        data = _handle_response(self._http.get("/v1/entities"))
        return [EntityResponse.model_validate(e) for e in data]

    def create_entity(self, data: dict[str, Any]) -> EntityResponse:
        """Create a new legal entity."""
        resp = _handle_response(self._http.post("/v1/entities", json=data))
        return EntityResponse.model_validate(resp)

    # -- Simulation ------------------------------------------------------------

    def simulate_pricing(
        self,
        plan_id: str,
        scenario: dict[str, Any],
    ) -> SimulationResult:
        """Run a pricing simulation against historical data."""
        payload: dict[str, Any] = {
            "plan_id": plan_id,
            "scenario": scenario,
        }
        data = _handle_response(self._http.post("/v1/simulate", json=payload))
        return SimulationResult.model_validate(data)

    # -- Lifecycle -------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncClient:
    """Asynchronous Rupiv API client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=_build_headers(api_key),
            timeout=timeout,
        )

    # -- Events ----------------------------------------------------------------

    async def track_event(
        self,
        metric: str,
        customer_id: str,
        properties: dict | None = None,
        idempotency_key: str | None = None,
    ) -> EventResponse:
        """Track a usage event (e.g. API call, message sent)."""
        payload = _event_payload(metric, customer_id, "usage", properties, idempotency_key)
        data = _handle_response(await self._http.post("/v1/events", json=payload))
        return EventResponse.model_validate(data)

    async def track_outcome(
        self,
        metric: str,
        customer_id: str,
        properties: dict | None = None,
        idempotency_key: str | None = None,
    ) -> EventResponse:
        """Track a business outcome (e.g. ticket resolved, lead generated)."""
        payload = _event_payload(metric, customer_id, "outcome", properties, idempotency_key)
        data = _handle_response(await self._http.post("/v1/events", json=payload))
        return EventResponse.model_validate(data)

    # -- Customers -------------------------------------------------------------

    async def get_customer(self, customer_id: str) -> CustomerResponse:
        """Fetch a customer by ID."""
        data = _handle_response(await self._http.get(f"/v1/customers/{customer_id}"))
        return CustomerResponse.model_validate(data)

    # -- Invoices --------------------------------------------------------------

    async def list_invoices(self, customer_id: str | None = None) -> list[InvoiceResponse]:
        """List invoices, optionally filtered by customer."""
        params: dict[str, str] = {}
        if customer_id is not None:
            params["customer_id"] = customer_id
        data = _handle_response(await self._http.get("/v1/invoices", params=params))
        return [InvoiceResponse.model_validate(inv) for inv in data]

    # -- Quotes ----------------------------------------------------------------

    async def create_quote(
        self,
        customer_id: str,
        plan_id: str,
        discount_pct: float = 0,
        term_months: int = 12,
        idempotency_key: str | None = None,
    ) -> QuoteResponse:
        """Create a new quote for a customer."""
        payload: dict[str, Any] = {
            "customer_id": customer_id,
            "plan_id": plan_id,
            "discount_pct": discount_pct,
            "term_months": term_months,
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
        }
        data = _handle_response(await self._http.post("/v1/quotes", json=payload))
        return QuoteResponse.model_validate(data)

    async def get_quote(self, quote_id: str) -> QuoteResponse:
        """Fetch a single quote by ID."""
        data = _handle_response(await self._http.get(f"/v1/quotes/{quote_id}"))
        return QuoteResponse.model_validate(data)

    async def list_quotes(
        self,
        customer_id: str | None = None,
        status: str | None = None,
    ) -> list[QuoteResponse]:
        """List quotes, optionally filtered by customer and/or status."""
        params: dict[str, str] = {}
        if customer_id is not None:
            params["customer_id"] = customer_id
        if status is not None:
            params["status"] = status
        data = _handle_response(await self._http.get("/v1/quotes", params=params))
        return [QuoteResponse.model_validate(q) for q in data]

    async def send_quote(self, quote_id: str) -> QuoteResponse:
        """Send a draft quote to the customer."""
        data = _handle_response(await self._http.post(f"/v1/quotes/{quote_id}/send"))
        return QuoteResponse.model_validate(data)

    async def accept_quote(self, quote_id: str) -> AcceptResponse:
        """Accept a quote, creating a subscription and revenue schedule."""
        data = _handle_response(await self._http.post(f"/v1/quotes/{quote_id}/accept"))
        return AcceptResponse.model_validate(data)

    async def reject_quote(self, quote_id: str, reason: str) -> QuoteResponse:
        """Reject a quote with a reason."""
        data = _handle_response(
            await self._http.post(f"/v1/quotes/{quote_id}/reject", json={"reason": reason}),
        )
        return QuoteResponse.model_validate(data)

    # -- Credits ---------------------------------------------------------------

    async def get_credits(self, customer_id: str) -> CreditBalanceResponse:
        """Fetch a customer's credit balance."""
        data = _handle_response(await self._http.get(f"/v1/credits/{customer_id}/balance"))
        return CreditBalanceResponse.model_validate(data)

    async def purchase_credits(
        self,
        customer_id: str,
        amount: int,
        idempotency_key: str | None = None,
    ) -> CreditBalanceResponse:
        """Purchase credits for a customer."""
        payload: dict[str, Any] = {
            "customer_id": customer_id,
            "amount": amount,
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
        }
        data = _handle_response(await self._http.post("/v1/credits/purchase", json=payload))
        return CreditBalanceResponse.model_validate(data)

    # -- Entities --------------------------------------------------------------

    async def list_entities(self) -> list[EntityResponse]:
        """List all legal entities."""
        data = _handle_response(await self._http.get("/v1/entities"))
        return [EntityResponse.model_validate(e) for e in data]

    async def create_entity(self, data: dict[str, Any]) -> EntityResponse:
        """Create a new legal entity."""
        resp = _handle_response(await self._http.post("/v1/entities", json=data))
        return EntityResponse.model_validate(resp)

    # -- Simulation ------------------------------------------------------------

    async def simulate_pricing(
        self,
        plan_id: str,
        scenario: dict[str, Any],
    ) -> SimulationResult:
        """Run a pricing simulation against historical data."""
        payload: dict[str, Any] = {
            "plan_id": plan_id,
            "scenario": scenario,
        }
        data = _handle_response(await self._http.post("/v1/simulate", json=payload))
        return SimulationResult.model_validate(data)

    # -- Lifecycle -------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
