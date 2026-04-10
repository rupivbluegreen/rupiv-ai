"""Tests for the alert worker check logic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.alert import Alert, AlertRule
from rupiv.models.customer import Customer
from rupiv.models.invoice import Invoice
from rupiv.models.subscription import Subscription, SubscriptionStatus
from rupiv.workers.alert_worker import run_checks


CUSTOMER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
async def alert_setup(db_session: AsyncSession) -> None:
    """Seed a customer, subscription, invoices, and an MRR drop alert rule."""
    customer = Customer(
        id=CUSTOMER_ID,
        name="Alert Test Corp",
        email="alert@test.example.com",
        external_id="ext-alert-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer)

    sub = Subscription(
        id=uuid.uuid4(),
        customer_id=CUSTOMER_ID,
        plan_id=uuid.uuid4(),
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.now(UTC) - timedelta(days=15),
        current_period_end=datetime.now(UTC) + timedelta(days=15),
    )
    db_session.add(sub)

    # Historical invoices: 3 periods of ~1000 EUR each (clearly in past)
    now = datetime.now(UTC)
    for i in range(1, 4):
        # Place created_at solidly in the middle of each historical period
        created = now - timedelta(days=32 + 30 * (i - 1))
        period_end = created + timedelta(days=15)
        inv = Invoice(
            id=uuid.uuid4(),
            customer_id=CUSTOMER_ID,
            subscription_id=sub.id,
            invoice_number=f"INV-HIST-{i:03d}",
            status="paid",
            currency="EUR",
            subtotal="1000.0000",
            tax_amount="210.0000",
            total="1210.0000",
            period_start=created - timedelta(days=15),
            period_end=period_end,
            due_date=(period_end + timedelta(days=14)).date(),
            created_at=created,
        )
        db_session.add(inv)

    # Current period: only 200 EUR (big drop vs 1210 historical)
    current_inv = Invoice(
        id=uuid.uuid4(),
        customer_id=CUSTOMER_ID,
        subscription_id=sub.id,
        invoice_number="INV-CURRENT-001",
        status="paid",
        currency="EUR",
        subtotal="165.0000",
        tax_amount="35.0000",
        total="200.0000",
        period_start=now - timedelta(days=25),
        period_end=now,
        due_date=(now + timedelta(days=14)).date(),
        created_at=now - timedelta(days=5),
    )
    db_session.add(current_inv)

    # Alert rule: MRR drop > 20%
    rule = AlertRule(
        id=uuid.uuid4(),
        name="MRR drop > 20%",
        alert_type="mrr_drop",
        threshold_pct="20.00",
        lookback_periods=3,
        is_active=True,
    )
    db_session.add(rule)

    await db_session.commit()


class TestRunChecks:
    """Tests for alert worker check cycle."""

    async def test_detects_mrr_drop(
        self, db_session: AsyncSession, alert_setup: None,
    ) -> None:
        created = await run_checks(db_session)
        assert created >= 1

        # Verify alert was persisted
        from sqlalchemy import select

        result = await db_session.execute(
            select(Alert).where(Alert.alert_type == "mrr_drop"),
        )
        alert = result.scalar_one_or_none()
        assert alert is not None
        assert alert.status == "open"
        assert "mrr" in (alert.metric_name or "").lower()

    async def test_dedup_skips_existing_open_alert(
        self, db_session: AsyncSession, alert_setup: None,
    ) -> None:
        # First run creates alert
        first = await run_checks(db_session)
        await db_session.commit()

        # Second run should skip (dedup)
        second = await run_checks(db_session)
        assert second == 0

    async def test_no_rules_no_alerts(self, db_session: AsyncSession) -> None:
        created = await run_checks(db_session)
        assert created == 0
