"""Tests for alert API endpoints."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.alert import Alert, AlertRule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded_alerts(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    """Seed alert rules and alerts, returning their IDs."""
    rule = AlertRule(
        id=uuid.uuid4(),
        name="MRR drop > 20%",
        alert_type="mrr_drop",
        threshold_pct="20.00",
        lookback_periods=3,
        is_active=True,
    )
    db_session.add(rule)

    alert_open = Alert(
        id=uuid.uuid4(),
        alert_type="mrr_drop",
        severity="critical",
        title="MRR dropped 35%",
        description="MRR fell from 10000 to 6500",
        metric_name="mrr",
        expected_value="10000.0000",
        actual_value="6500.0000",
        status="open",
    )
    db_session.add(alert_open)

    alert_resolved = Alert(
        id=uuid.uuid4(),
        alert_type="usage_spike",
        severity="warning",
        title="Usage spike on api_call",
        status="resolved",
    )
    db_session.add(alert_resolved)

    await db_session.commit()

    return {
        "rule_id": rule.id,
        "alert_open_id": alert_open.id,
        "alert_resolved_id": alert_resolved.id,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListAlerts:
    """Tests for GET /v1/alerts."""

    async def test_list_all(
        self, client: AsyncClient, seeded_alerts: dict[str, uuid.UUID],
    ) -> None:
        resp = await client.get("/v1/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    async def test_filter_by_status(
        self, client: AsyncClient, seeded_alerts: dict[str, uuid.UUID],
    ) -> None:
        resp = await client.get("/v1/alerts?status=open")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "open"


class TestUpdateAlert:
    """Tests for PATCH /v1/alerts/{id}."""

    async def test_acknowledge(
        self, client: AsyncClient, seeded_alerts: dict[str, uuid.UUID],
    ) -> None:
        alert_id = seeded_alerts["alert_open_id"]
        resp = await client.patch(
            f"/v1/alerts/{alert_id}",
            json={"status": "acknowledged"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

    async def test_resolve(
        self, client: AsyncClient, seeded_alerts: dict[str, uuid.UUID],
    ) -> None:
        alert_id = seeded_alerts["alert_open_id"]
        resp = await client.patch(
            f"/v1/alerts/{alert_id}",
            json={"status": "resolved"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"
        assert resp.json()["resolved_at"] is not None

    async def test_not_found(self, client: AsyncClient, seeded_alerts: Any) -> None:  # noqa: ANN401
        resp = await client.patch(
            f"/v1/alerts/{uuid.uuid4()}",
            json={"status": "resolved"},
        )
        assert resp.status_code == 404


class TestAlertRules:
    """Tests for alert rule CRUD."""

    async def test_create_rule(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/v1/alert-rules",
            json={
                "name": "Usage spike > 50%",
                "alert_type": "usage_spike",
                "threshold_pct": 50,
                "lookback_periods": 3,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Usage spike > 50%"
        assert data["is_active"] is True

    async def test_list_rules(
        self, client: AsyncClient, seeded_alerts: dict[str, uuid.UUID],
    ) -> None:
        resp = await client.get("/v1/alert-rules")
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) >= 1

    async def test_update_rule(
        self, client: AsyncClient, seeded_alerts: dict[str, uuid.UUID],
    ) -> None:
        rule_id = seeded_alerts["rule_id"]
        resp = await client.patch(
            f"/v1/alert-rules/{rule_id}",
            json={"threshold_pct": 30, "is_active": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is False
