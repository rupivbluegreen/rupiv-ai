"""Shared pytest fixtures for Rupiv.ai test suite.

Uses an in-memory SQLite database (via aiosqlite) so that tests never require
PostgreSQL, Redis, or ClickHouse to be running.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

# Set environment variables BEFORE any rupiv imports, so that the module-level
# ``app = create_app()`` in main.py picks up test-safe values and the .env
# file does not cause parse errors.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CLICKHOUSE_URL", "http://localhost:8123")
os.environ.setdefault("CLICKHOUSE_DATABASE", "rupiv_test")
os.environ.setdefault("CORS_ORIGINS", '["http://testserver"]')

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from rupiv.config import Settings, get_settings
from rupiv.db import Base, get_db

# ---------------------------------------------------------------------------
# SQLite compatibility: make PostgreSQL-specific types renderable on SQLite
# ---------------------------------------------------------------------------


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:  # noqa: ANN401
    return compiler.visit_JSON(JSON(), **kw)


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:  # noqa: ANN401
    return "VARCHAR(36)"


# ---------------------------------------------------------------------------
# Test settings
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///"


def _test_settings() -> Settings:
    """Return a Settings instance suitable for testing.

    Overrides URLs so no real external service is needed.
    """
    return Settings(
        DATABASE_URL=TEST_DATABASE_URL,
        REDIS_URL="redis://localhost:6379/15",
        CLICKHOUSE_URL="http://localhost:8123",
        CLICKHOUSE_DATABASE="rupiv_test",
        APP_ENV="test",
        APP_SECRET_KEY="test-secret-key",
        CORS_ORIGINS=["http://testserver"],
        _env_file=None,  # type: ignore[call-arg]
    )


# ---------------------------------------------------------------------------
# Database engine & session fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """Create an in-memory SQLite async engine with all tables."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Disable FK enforcement in SQLite (models have cross-table FKs that
    # would require insertion order we don't want to worry about in tests).
    @sa_event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: Any, _rec: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    # Import all models so metadata is fully populated
    import rupiv.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Provide an async SQLAlchemy session backed by the test SQLite engine."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Application fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def app(
    db_engine: AsyncEngine,
) -> AsyncIterator[Any]:
    """Return a FastAPI app with dependencies overridden for testing.

    The real lifespan is replaced with a no-op so Redis / ClickHouse are
    never contacted.
    """
    from fastapi import FastAPI

    from rupiv.main import create_app

    # Patch the lifespan to a no-op before creating the app
    @asynccontextmanager
    async def _noop_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    with patch("rupiv.main._lifespan", _noop_lifespan):
        test_app: FastAPI = create_app()

    # Override the get_db dependency to use our test engine
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    test_app.dependency_overrides[get_db] = _override_get_db
    test_app.dependency_overrides[get_settings] = _test_settings

    yield test_app

    test_app.dependency_overrides.clear()


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    """Yield an ``httpx.AsyncClient`` wired to the test FastAPI app.

    Uses ``ASGITransport`` so requests never hit the network.
    """
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Factory data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_customer_id() -> uuid.UUID:
    """A stable UUID for the sample customer."""
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
async def sample_customer(
    db_session: AsyncSession,
    sample_customer_id: uuid.UUID,
) -> dict[str, Any]:
    """Insert and return a sample customer in the test DB."""
    from rupiv.models.customer import Customer

    customer = Customer(
        id=sample_customer_id,
        name="Acme AI Corp",
        email="billing@acme-ai.example.com",
        external_id="ext-acme-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer)
    await db_session.commit()

    return {
        "id": sample_customer_id,
        "name": "Acme AI Corp",
        "email": "billing@acme-ai.example.com",
        "external_id": "ext-acme-001",
        "country_code": "NL",
    }


@pytest.fixture
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


@pytest.fixture
def sample_event(sample_customer_id: uuid.UUID) -> dict[str, Any]:
    """Return a dictionary representing a sample usage/outcome event payload."""
    return {
        "type": "outcome",
        "metric": "ticket_resolved",
        "customer_id": str(sample_customer_id),
        "properties": {
            "resolution_time": 45,
            "escalated": False,
            "csat_score": 4.8,
        },
        "idempotency_key": "idem-test-001",
    }


def make_event_payload(
    *,
    event_type: str = "usage",
    metric: str = "api_call",
    customer_id: str | uuid.UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    properties: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Factory helper to build event payloads for POST /v1/events."""
    return {
        "type": event_type,
        "metric": metric,
        "customer_id": str(customer_id),
        "properties": properties or {},
        "idempotency_key": idempotency_key or f"idem-{uuid.uuid4().hex[:12]}",
    }
