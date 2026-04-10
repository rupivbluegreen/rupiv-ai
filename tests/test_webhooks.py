"""Tests for outbound webhook dispatch and delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.customer import Customer
from rupiv.models.webhook_endpoint import WebhookDelivery, WebhookEndpoint
from rupiv.webhooks.dispatcher import WEBHOOK_QUEUE_KEY


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CUSTOMER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

_test_customer: Customer | None = None


@pytest.fixture
async def webhook_setup(db_session: AsyncSession) -> dict[str, Any]:
    """Seed a customer with a webhook endpoint."""
    global _test_customer  # noqa: PLW0603

    customer = Customer(
        id=CUSTOMER_ID,
        name="Webhook Test Corp",
        email="wh@test.example.com",
        external_id="ext-wh-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer)

    endpoint = WebhookEndpoint(
        id=uuid.uuid4(),
        customer_id=CUSTOMER_ID,
        url="https://example.com/webhook",
        secret="test-secret-key-12345",
        events=["invoice.paid", "payment.failed"],
        is_active=True,
        failure_count=0,
    )
    db_session.add(endpoint)

    await db_session.commit()

    from sqlalchemy import select

    result = await db_session.execute(select(Customer).where(Customer.id == CUSTOMER_ID))
    _test_customer = result.scalar_one()

    return {"customer_id": CUSTOMER_ID, "endpoint_id": endpoint.id}


@pytest.fixture
async def webhook_client(
    app: Any,  # noqa: ANN401
    db_engine: Any,  # noqa: ANN401
    db_session: AsyncSession,
    webhook_setup: dict[str, Any],
) -> AsyncClient:
    """Client with auth overridden for webhook endpoint tests."""
    from httpx import ASGITransport

    from rupiv.api.middleware.auth import get_current_customer

    async def _override() -> Customer:
        assert _test_customer is not None
        return _test_customer

    app.dependency_overrides[get_current_customer] = _override

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.pop(get_current_customer, None)


# ---------------------------------------------------------------------------
# Dispatcher tests
# ---------------------------------------------------------------------------


class TestDispatcher:
    """Tests for the webhook event dispatcher."""

    def test_queue_key_defined(self) -> None:
        assert WEBHOOK_QUEUE_KEY == "rupiv:webhooks:outbound"


# ---------------------------------------------------------------------------
# Signing tests
# ---------------------------------------------------------------------------


class TestSigning:
    """Tests for HMAC-SHA256 webhook signature."""

    def test_sign_payload(self) -> None:
        from rupiv.workers.webhook_worker import _sign_payload

        payload = b'{"event_type":"invoice.paid","data":{}}'
        secret = "test-secret"
        sig = _sign_payload(payload, secret)
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert sig == expected


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestWebhookEndpointAPI:
    """Tests for webhook endpoint CRUD."""

    async def test_create_endpoint(
        self, webhook_client: AsyncClient, webhook_setup: dict[str, Any],
    ) -> None:
        resp = await webhook_client.post(
            "/v1/webhook-endpoints",
            json={"url": "https://new.example.com/hook", "events": ["invoice.created"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://new.example.com/hook"
        assert data["events"] == ["invoice.created"]
        assert data["is_active"] is True
        assert len(data["secret"]) > 0

    async def test_list_endpoints(
        self, webhook_client: AsyncClient, webhook_setup: dict[str, Any],
    ) -> None:
        resp = await webhook_client.get("/v1/webhook-endpoints")
        assert resp.status_code == 200
        endpoints = resp.json()
        assert len(endpoints) >= 1

    async def test_delete_endpoint(
        self, webhook_client: AsyncClient, webhook_setup: dict[str, Any],
    ) -> None:
        endpoint_id = webhook_setup["endpoint_id"]
        resp = await webhook_client.delete(f"/v1/webhook-endpoints/{endpoint_id}")
        assert resp.status_code == 204

    async def test_delete_not_found(
        self, webhook_client: AsyncClient, webhook_setup: dict[str, Any],
    ) -> None:
        resp = await webhook_client.delete(f"/v1/webhook-endpoints/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_list_deliveries_empty(
        self, webhook_client: AsyncClient, webhook_setup: dict[str, Any],
    ) -> None:
        endpoint_id = webhook_setup["endpoint_id"]
        resp = await webhook_client.get(f"/v1/webhook-endpoints/{endpoint_id}/deliveries")
        assert resp.status_code == 200
        assert resp.json() == []
