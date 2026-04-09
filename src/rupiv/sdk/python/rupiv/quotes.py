"""Quote lifecycle management for the Rupiv API."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from .types import AcceptResponse, QuoteResponse, RupivError


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


class QuoteClient:
    """Synchronous quote operations for the Rupiv API.

    This is a standalone client focused on the quotes lifecycle.
    The same methods are also available on :class:`rupiv.Client`.

    Usage::

        from rupiv.quotes import QuoteClient

        qc = QuoteClient(api_key="rp_live_xxx")
        quote = qc.create_quote(customer_id="cust_123", plan_id="plan_abc")
        qc.send_quote(quote.id)
        qc.close()
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.rupiv.ai",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "rupiv-python/0.1.0",
            },
            timeout=timeout,
        )

    # -- Quote lifecycle -------------------------------------------------------

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
            self._http.post(
                f"/v1/quotes/{quote_id}/reject",
                json={"reason": reason},
            ),
        )
        return QuoteResponse.model_validate(data)

    # -- Lifecycle -------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> QuoteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncQuoteClient:
    """Asynchronous quote operations for the Rupiv API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.rupiv.ai",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "rupiv-python/0.1.0",
            },
            timeout=timeout,
        )

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
            await self._http.post(
                f"/v1/quotes/{quote_id}/reject",
                json={"reason": reason},
            ),
        )
        return QuoteResponse.model_validate(data)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncQuoteClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
