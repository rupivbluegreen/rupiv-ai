"""Tests for the event ingestion endpoint POST /v1/events."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_usage_event_returns_202(
    client: AsyncClient,
    sample_event: dict[str, Any],
) -> None:
    """POST /v1/events with a valid usage event should return 202 Accepted."""
    payload = {**sample_event, "type": "usage", "metric": "api_call"}
    response = await client.post("/v1/events", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    # Verify the response contains a valid UUID for event_id.
    uuid.UUID(body["event_id"])


@pytest.mark.asyncio
async def test_create_outcome_event_returns_202(
    client: AsyncClient,
    sample_event: dict[str, Any],
) -> None:
    """POST /v1/events with a valid outcome event should return 202 Accepted."""
    response = await client.post("/v1/events", json=sample_event)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    uuid.UUID(body["event_id"])


@pytest.mark.asyncio
async def test_create_event_missing_fields_returns_422(
    client: AsyncClient,
) -> None:
    """POST /v1/events with missing required fields should return 422."""
    # Send an empty body — metric, customer_id, type, and idempotency_key are required.
    response = await client.post("/v1/events", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_event_invalid_type_returns_422(
    client: AsyncClient,
    sample_event: dict[str, Any],
) -> None:
    """POST /v1/events with an invalid event type should return 422."""
    payload = {**sample_event, "type": "unknown_type"}
    response = await client.post("/v1/events", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.skip(reason="Idempotency deduplication not yet implemented")
async def test_idempotency_key_deduplication(
    client: AsyncClient,
    sample_event: dict[str, Any],
) -> None:
    """Sending the same idempotency_key twice should return the same event_id."""
    first = await client.post("/v1/events", json=sample_event)
    second = await client.post("/v1/events", json=sample_event)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["event_id"] == second.json()["event_id"]
