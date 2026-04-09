"""Tests for audit logging and GDPR compliance tooling."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.compliance.audit import get_audit_trail, log_action
from rupiv.compliance.data_export import (
    anonymize_customer,
    export_customer_data,
)
from rupiv.models.audit_log import AuditLog
from rupiv.models.customer import Customer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
RESOURCE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
CUSTOMER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


async def _insert_customer(session: AsyncSession) -> Customer:
    """Insert a minimal customer for GDPR tests."""
    customer = Customer(
        id=CUSTOMER_ID,
        name="Test User",
        email="test@example.com",
        external_id="ext-test-001",
        country_code="NL",
        is_business=False,
        currency="EUR",
        billing_email="billing@example.com",
        vat_number="NL123456789B01",
    )
    session.add(customer)
    await session.flush()
    return customer


# ---------------------------------------------------------------------------
# Audit log tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_action(db_session: AsyncSession) -> None:
    """log_action creates an append-only audit entry."""
    entry = await log_action(
        db_session,
        actor_id=ACTOR_ID,
        actor_type="user",
        action="create",
        resource_type="customer",
        resource_id=RESOURCE_ID,
        changes={"name": {"old": None, "new": "Acme"}},
        ip_address="127.0.0.1",
        user_agent="pytest/1.0",
    )

    assert isinstance(entry, AuditLog)
    assert entry.actor_id == ACTOR_ID
    assert entry.action == "create"
    assert entry.resource_type == "customer"
    assert entry.resource_id == RESOURCE_ID
    assert entry.changes == {"name": {"old": None, "new": "Acme"}}
    assert entry.ip_address == "127.0.0.1"
    assert entry.user_agent == "pytest/1.0"
    assert entry.id is not None


@pytest.mark.asyncio
async def test_get_audit_trail(db_session: AsyncSession) -> None:
    """get_audit_trail returns entries for a specific resource."""
    # Create two entries for the same resource
    for action in ("create", "update"):
        await log_action(
            db_session,
            actor_id=ACTOR_ID,
            actor_type="user",
            action=action,
            resource_type="invoice",
            resource_id=RESOURCE_ID,
        )

    # Create one entry for a different resource
    other_id = uuid.uuid4()
    await log_action(
        db_session,
        actor_id=ACTOR_ID,
        actor_type="user",
        action="create",
        resource_type="invoice",
        resource_id=other_id,
    )

    await db_session.flush()

    trail = await get_audit_trail(
        db_session,
        resource_type="invoice",
        resource_id=RESOURCE_ID,
    )

    assert len(trail) == 2
    actions = {e.action for e in trail}
    assert actions == {"create", "update"}


# ---------------------------------------------------------------------------
# GDPR data export tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_customer_data(db_session: AsyncSession) -> None:
    """export_customer_data returns all PII for a customer."""
    await _insert_customer(db_session)

    export = await export_customer_data(
        db_session, CUSTOMER_ID, actor_id=ACTOR_ID
    )

    assert "customer" in export
    customer_data: dict[str, Any] = export["customer"]
    assert customer_data["id"] == str(CUSTOMER_ID)
    assert customer_data["name"] == "Test User"
    assert customer_data["email"] == "test@example.com"
    assert customer_data["billing_email"] == "billing@example.com"
    assert customer_data["vat_number"] == "NL123456789B01"
    assert "export_generated_at" in export


@pytest.mark.asyncio
async def test_anonymize_customer(db_session: AsyncSession) -> None:
    """anonymize_customer replaces PII with [REDACTED]."""
    await _insert_customer(db_session)

    result = await anonymize_customer(
        db_session, CUSTOMER_ID, actor_id=ACTOR_ID
    )
    await db_session.flush()

    assert result["customer_id"] == str(CUSTOMER_ID)
    assert "name" in result["anonymized_fields"]
    assert "email" in result["anonymized_fields"]

    # Verify the customer record is actually anonymized
    from sqlalchemy import select

    stmt = select(Customer).where(Customer.id == CUSTOMER_ID)
    row = await db_session.execute(stmt)
    customer = row.scalar_one()

    assert customer.name == "[REDACTED]"
    assert customer.email == "[REDACTED]"
    assert customer.billing_email == "[REDACTED]"
    assert customer.vat_number == "[REDACTED]"
    assert customer.metadata_ is None
