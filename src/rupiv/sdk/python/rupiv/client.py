"""Synchronous and asynchronous HTTP clients for the Rupiv API."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from .types import CustomerResponse, EventResponse, InvoiceResponse, RupivError

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

    # -- Lifecycle -------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
