"""Tests for the /health endpoint and API-level basics."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from rupiv import __version__


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health should return 200 with status ok and the current version."""
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


@pytest.mark.asyncio
async def test_health_json_content_type(client: AsyncClient) -> None:
    """GET /health should return application/json content type."""
    response = await client.get("/health")

    assert response.headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_api_version_in_openapi(client: AsyncClient) -> None:
    """The OpenAPI schema should advertise the current API version."""
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["version"] == __version__
