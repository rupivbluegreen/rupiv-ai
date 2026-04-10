"""Tests for customer self-service portal endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.customer import Customer
from rupiv.models.event import Event
from rupiv.models.invoice import Invoice, InvoiceLineItem
from rupiv.models.subscription import Subscription, SubscriptionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CUSTOMER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SUBSCRIPTION_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
INVOICE_ID = uuid.UUID("22222222-3333-4444-5555-666666666666")
OTHER_INVOICE_ID = uuid.UUID("33333333-4444-5555-6666-777777777777")
OTHER_CUSTOMER_ID = uuid.UUID("99999999-8888-7777-6666-555555555555")


async def _seed_portal_data(session: AsyncSession) -> None:
    """Seed a customer, subscription, invoice, and events for portal tests."""
    customer = Customer(
        id=CUSTOMER_ID,
        name="Portal Test Corp",
        email="portal@test.example.com",
        external_id="ext-portal-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    session.add(customer)

    # Another customer (for ownership checks)
    other_customer = Customer(
        id=OTHER_CUSTOMER_ID,
        name="Other Corp",
        email="other@test.example.com",
        external_id="ext-other-001",
        country_code="DE",
        is_business=True,
        currency="EUR",
    )
    session.add(other_customer)

    now = datetime.now(UTC)
    subscription = Subscription(
        id=SUBSCRIPTION_ID,
        customer_id=CUSTOMER_ID,
        plan_id=uuid.uuid4(),
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now - timedelta(days=15),
        current_period_end=now + timedelta(days=15),
    )
    session.add(subscription)

    invoice = Invoice(
        id=INVOICE_ID,
        customer_id=CUSTOMER_ID,
        subscription_id=SUBSCRIPTION_ID,
        invoice_number="INV-2026-0001",
        status="open",
        currency="EUR",
        subtotal="100.0000",
        tax_amount="21.0000",
        total="121.0000",
        period_start=now - timedelta(days=30),
        period_end=now,
        due_date=(now + timedelta(days=14)).date(),
    )
    session.add(invoice)

    line_item = InvoiceLineItem(
        id=uuid.uuid4(),
        invoice_id=INVOICE_ID,
        description="API calls",
        metric="api_call",
        quantity="1000.0000",
        unit_amount="0.1000",
        amount="100.0000",
    )
    session.add(line_item)

    # Invoice belonging to other customer
    other_invoice = Invoice(
        id=OTHER_INVOICE_ID,
        customer_id=OTHER_CUSTOMER_ID,
        subscription_id=uuid.uuid4(),
        invoice_number="INV-2026-0002",
        status="paid",
        currency="EUR",
        subtotal="50.0000",
        tax_amount="9.5000",
        total="59.5000",
        period_start=now - timedelta(days=30),
        period_end=now,
        due_date=(now + timedelta(days=14)).date(),
    )
    session.add(other_invoice)

    # Events for the customer
    for i in range(3):
        event = Event(
            id=uuid.uuid4(),
            customer_id=CUSTOMER_ID,
            event_type="usage",
            metric="api_call",
            properties={},
            idempotency_key=f"portal-test-{i}",
            timestamp=now - timedelta(days=i),
        )
        session.add(event)

    await session.commit()


_test_customer: Customer | None = None


def _mock_get_current_customer() -> Any:
    """Return a dependency override that returns the seeded test customer."""

    async def _override() -> Customer:
        assert _test_customer is not None, "Test customer not seeded"
        return _test_customer

    return _override


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def portal_client(
    app: Any,  # noqa: ANN401
    db_engine: Any,  # noqa: ANN401
    db_session: AsyncSession,
) -> AsyncClient:
    """Yield a client with portal auth overridden to return our test customer."""
    global _test_customer  # noqa: PLW0603

    from httpx import ASGITransport

    from rupiv.api.middleware.auth import get_current_customer

    await _seed_portal_data(db_session)

    # Load the customer from DB to get a fully populated object
    from sqlalchemy import select

    result = await db_session.execute(select(Customer).where(Customer.id == CUSTOMER_ID))
    _test_customer = result.scalar_one()

    app.dependency_overrides[get_current_customer] = _mock_get_current_customer()

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.pop(get_current_customer, None)
    _test_customer = None


class TestPortalMe:
    """Tests for GET /v1/portal/me."""

    async def test_returns_customer_profile(self, portal_client: AsyncClient) -> None:
        resp = await portal_client.get("/v1/portal/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Portal Test Corp"
        assert data["email"] == "portal@test.example.com"
        assert data["country_code"] == "NL"
        assert data["currency"] == "EUR"
        assert data["is_business"] is True


class TestPortalInvoices:
    """Tests for GET /v1/portal/invoices and /v1/portal/invoices/{id}."""

    async def test_list_returns_only_own_invoices(self, portal_client: AsyncClient) -> None:
        resp = await portal_client.get("/v1/portal/invoices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == str(INVOICE_ID)

    async def test_get_own_invoice(self, portal_client: AsyncClient) -> None:
        resp = await portal_client.get(f"/v1/portal/invoices/{INVOICE_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == "121.0000"
        assert len(data["line_items"]) == 1

    async def test_cannot_access_other_customers_invoice(
        self, portal_client: AsyncClient,
    ) -> None:
        resp = await portal_client.get(f"/v1/portal/invoices/{OTHER_INVOICE_ID}")
        assert resp.status_code == 404


class TestPortalUsage:
    """Tests for GET /v1/portal/usage."""

    async def test_returns_usage_metrics(self, portal_client: AsyncClient) -> None:
        resp = await portal_client.get("/v1/portal/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer_id"] == str(CUSTOMER_ID)
        assert len(data["metrics"]) >= 1
        api_metric = next((m for m in data["metrics"] if m["metric"] == "api_call"), None)
        assert api_metric is not None
        assert api_metric["count"] >= 1


class TestPortalSubscription:
    """Tests for GET /v1/portal/subscription."""

    async def test_returns_active_subscription(self, portal_client: AsyncClient) -> None:
        resp = await portal_client.get("/v1/portal/subscription")
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["id"] == str(SUBSCRIPTION_ID)
        assert data["status"] == "active"
