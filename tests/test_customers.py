"""Tests for customer CRUD endpoints — /v1/customers."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_customer(client: AsyncClient) -> None:
    """POST /v1/customers with valid payload returns 201 and correct fields."""
    payload: dict[str, Any] = {
        "name": "Acme AI Corp",
        "email": "billing@acme-ai.example.com",
        "external_id": "ext-acme-001",
        "country_code": "NL",
        "currency": "EUR",
        "is_business": True,
    }

    response = await client.post("/v1/customers", json=payload)

    assert response.status_code == 201
    body: dict[str, Any] = response.json()

    # Verify returned fields match the request
    assert body["name"] == payload["name"]
    assert body["email"] == payload["email"]
    assert body["external_id"] == payload["external_id"]
    assert body["country_code"] == payload["country_code"]
    assert body["currency"] == payload["currency"]
    assert body["is_business"] is True

    # Server should assign a valid UUID id and timestamps
    uuid.UUID(body["id"])
    assert "created_at" in body
    assert "updated_at" in body


async def test_create_customer_missing_fields(client: AsyncClient) -> None:
    """POST /v1/customers with missing required fields returns 422."""
    response = await client.post("/v1/customers", json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_customers_empty(client: AsyncClient) -> None:
    """GET /v1/customers on an empty database returns an empty list."""
    response = await client.get("/v1/customers")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_customers_with_data(client: AsyncClient) -> None:
    """Create 3 customers, then GET /v1/customers returns all 3."""
    for i in range(3):
        payload: dict[str, Any] = {
            "name": f"Customer {i}",
            "email": f"c{i}@example.com",
            "external_id": f"ext-{i}",
        }
        resp = await client.post("/v1/customers", json=payload)
        assert resp.status_code == 201

    response = await client.get("/v1/customers")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


async def test_get_customer(client: AsyncClient) -> None:
    """Create a customer, then GET by ID returns the same fields."""
    payload: dict[str, Any] = {
        "name": "Test Corp",
        "email": "test@corp.com",
        "external_id": "ext-test-get",
        "country_code": "DE",
        "currency": "EUR",
        "is_business": True,
    }
    create_resp = await client.post("/v1/customers", json=payload)
    assert create_resp.status_code == 201
    customer_id: str = create_resp.json()["id"]

    response = await client.get(f"/v1/customers/{customer_id}")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["id"] == customer_id
    assert body["name"] == "Test Corp"
    assert body["email"] == "test@corp.com"
    assert body["country_code"] == "DE"


async def test_get_customer_not_found(client: AsyncClient) -> None:
    """GET /v1/customers/<random-uuid> returns 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/v1/customers/{random_id}")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def test_update_customer(client: AsyncClient) -> None:
    """Create a customer, then PATCH with new fields, verify update."""
    create_resp = await client.post(
        "/v1/customers",
        json={
            "name": "Old Name",
            "email": "old@example.com",
            "external_id": "ext-update-test",
            "country_code": "NL",
        },
    )
    assert create_resp.status_code == 201
    customer_id: str = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/v1/customers/{customer_id}",
        json={"name": "New Name", "email": "new@example.com"},
    )

    assert patch_resp.status_code == 200
    body: dict[str, Any] = patch_resp.json()
    assert body["name"] == "New Name"
    assert body["email"] == "new@example.com"


async def test_update_customer_partial(client: AsyncClient) -> None:
    """PATCH only name; verify other fields like email remain unchanged."""
    create_resp = await client.post(
        "/v1/customers",
        json={
            "name": "Original",
            "email": "keep@example.com",
            "external_id": "ext-partial-update",
            "country_code": "FR",
            "is_business": False,
        },
    )
    assert create_resp.status_code == 201
    customer_id: str = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/v1/customers/{customer_id}",
        json={"name": "Updated"},
    )

    assert patch_resp.status_code == 200
    body: dict[str, Any] = patch_resp.json()
    assert body["name"] == "Updated"
    # Other fields must be unchanged
    assert body["email"] == "keep@example.com"
    assert body["country_code"] == "FR"
    assert body["is_business"] is False
