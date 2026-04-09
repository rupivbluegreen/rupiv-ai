"""Shared pytest fixtures for Rupiv.ai test suite."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rupiv.main import create_app

# ---------------------------------------------------------------------------
# Application fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    """Return a fresh FastAPI application instance for testing.

    The lifespan is intentionally *not* triggered so that tests do not
    require PostgreSQL, Redis, or ClickHouse to be running.
    """
    from fastapi import FastAPI

    test_app: FastAPI = create_app()
    return test_app


@pytest.fixture()
async def client(app) -> AsyncIterator[AsyncClient]:
    """Yield an ``httpx.AsyncClient`` wired to the test FastAPI app.

    Uses ``ASGITransport`` so requests never hit the network.
    """
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Database fixtures (SQLite async for unit tests)
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    """Provide an async SQLAlchemy session backed by an in-memory SQLite database.

    Tables are created from ``Base.metadata`` so that model-level tests can
    run without a real PostgreSQL instance.
    """
    from rupiv.db import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Factory data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_customer() -> dict[str, Any]:
    """Return a dictionary representing a sample customer."""
    return {
        "id": uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        "name": "Acme AI Corp",
        "email": "billing@acme-ai.example.com",
        "external_id": "ext-acme-001",
        "metadata": {"industry": "support_ai", "tier": "growth"},
    }


@pytest.fixture()
def sample_plan() -> dict[str, Any]:
    """Return a dictionary representing a sample billing plan."""
    return {
        "id": uuid.UUID("11111111-2222-3333-4444-555555555555"),
        "name": "Outcome Growth",
        "description": "Pay per resolved ticket",
        "currency": "EUR",
        "billing_period": "monthly",
        "pricing_rules": [
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "unit_price": "0.9900",
                "flat_amount": "0.0000",
                "outcome_rules": {
                    "billable_when": {
                        "escalated": False,
                        "resolution_time_lt": 300,
                        "csat_score_gte": 3.0,
                    },
                    "cap_per_period": 50000,
                },
            },
        ],
    }


@pytest.fixture()
def sample_event() -> dict[str, Any]:
    """Return a dictionary representing a sample usage/outcome event."""
    return {
        "type": "outcome",
        "metric": "ticket_resolved",
        "customer_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "properties": {
            "resolution_time": 45,
            "escalated": False,
            "csat_score": 4.8,
        },
        "idempotency_key": "idem-test-001",
    }
