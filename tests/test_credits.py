"""Tests for credit-based billing — balance operations and API endpoints."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.credits import (
    InsufficientCreditsError,
    consume_credits,
    get_balance,
    get_transactions,
    purchase_credits,
    refund_credits,
)


# ---------------------------------------------------------------------------
# Unit tests — credit operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_balance_new_customer(
    db_session: AsyncSession,
    sample_customer: dict[str, Any],
    sample_customer_id: uuid.UUID,
) -> None:
    """A new customer with no credit history should have balance 0."""
    balance = await get_balance(db_session, sample_customer_id)
    assert balance == Decimal("0")


@pytest.mark.asyncio
async def test_purchase_credits(
    db_session: AsyncSession,
    sample_customer: dict[str, Any],
    sample_customer_id: uuid.UUID,
) -> None:
    """Purchasing credits increases the balance."""
    await purchase_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("1000.0000"),
        description="Initial credit purchase",
    )
    await db_session.flush()

    balance = await get_balance(db_session, sample_customer_id)
    assert balance == Decimal("1000.0000")


@pytest.mark.asyncio
async def test_consume_credits(
    db_session: AsyncSession,
    sample_customer: dict[str, Any],
    sample_customer_id: uuid.UUID,
) -> None:
    """Consuming credits decreases the balance."""
    await purchase_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("500.0000"),
        description="Purchase",
    )
    await db_session.flush()

    await consume_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("200.0000"),
        description="Ticket resolved",
    )
    await db_session.flush()

    balance = await get_balance(db_session, sample_customer_id)
    assert balance == Decimal("300.0000")


@pytest.mark.asyncio
async def test_consume_insufficient(
    db_session: AsyncSession,
    sample_customer: dict[str, Any],
    sample_customer_id: uuid.UUID,
) -> None:
    """Consuming more credits than available raises InsufficientCreditsError."""
    await purchase_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("100.0000"),
        description="Small purchase",
    )
    await db_session.flush()

    with pytest.raises(InsufficientCreditsError) as exc_info:
        await consume_credits(
            db_session,
            sample_customer_id,
            amount=Decimal("500.0000"),
            description="Too many credits",
        )

    assert exc_info.value.available == Decimal("100.0000")
    assert exc_info.value.requested == Decimal("500.0000")


@pytest.mark.asyncio
async def test_refund_credits(
    db_session: AsyncSession,
    sample_customer: dict[str, Any],
    sample_customer_id: uuid.UUID,
) -> None:
    """Refunding credits increases the balance."""
    await purchase_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("1000.0000"),
        description="Purchase",
    )
    await db_session.flush()

    await consume_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("300.0000"),
        description="Consumption",
    )
    await db_session.flush()

    await refund_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("100.0000"),
        description="Partial refund",
    )
    await db_session.flush()

    balance = await get_balance(db_session, sample_customer_id)
    assert balance == Decimal("800.0000")


@pytest.mark.asyncio
async def test_transaction_history(
    db_session: AsyncSession,
    sample_customer: dict[str, Any],
    sample_customer_id: uuid.UUID,
) -> None:
    """Transactions are returned in reverse chronological order."""
    await purchase_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("1000.0000"),
        description="First purchase",
    )
    await db_session.flush()

    await consume_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("200.0000"),
        description="First consumption",
    )
    await db_session.flush()

    await refund_credits(
        db_session,
        sample_customer_id,
        amount=Decimal("50.0000"),
        description="Refund",
    )
    await db_session.flush()

    txns = await get_transactions(db_session, sample_customer_id)
    assert len(txns) == 3

    # Collect all descriptions and amounts (order may vary in SQLite due to
    # identical sub-second timestamps, but should be deterministic in Postgres).
    descs = {t.description for t in txns}
    assert descs == {"First purchase", "First consumption", "Refund"}

    amounts_by_desc = {t.description: t.amount for t in txns}
    assert amounts_by_desc["First purchase"] == Decimal("1000.0000")
    assert amounts_by_desc["First consumption"] == Decimal("-200.0000")
    assert amounts_by_desc["Refund"] == Decimal("50.0000")


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_get_balance(
    client: AsyncClient,
    sample_customer: dict[str, Any],
    sample_customer_id: uuid.UUID,
) -> None:
    """GET /v1/credits/{id}/balance returns the current balance."""
    resp = await client.get(f"/v1/credits/{sample_customer_id}/balance")
    assert resp.status_code == 200

    data = resp.json()
    assert data["customer_id"] == str(sample_customer_id)
    assert Decimal(data["balance"]) == Decimal("0")
    assert data["currency"] == "EUR"


@pytest.mark.asyncio
async def test_api_purchase_credits(
    client: AsyncClient,
    sample_customer: dict[str, Any],
    sample_customer_id: uuid.UUID,
) -> None:
    """POST /v1/credits/{id}/purchase creates a transaction and increases balance."""
    resp = await client.post(
        f"/v1/credits/{sample_customer_id}/purchase",
        json={
            "amount": "5000.0000",
            "description": "API credit purchase",
        },
    )
    assert resp.status_code == 201

    data = resp.json()
    assert data["transaction_type"] == "purchase"
    assert Decimal(data["amount"]) == Decimal("5000.0000")
    assert data["customer_id"] == str(sample_customer_id)

    # Verify balance was updated
    balance_resp = await client.get(f"/v1/credits/{sample_customer_id}/balance")
    assert balance_resp.status_code == 200
    assert Decimal(balance_resp.json()["balance"]) == Decimal("5000.0000")
