"""Tests for ERP export formatters and API."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.erp.formatters import format_entries, to_csv, to_quickbooks_iif, to_xero_csv
from rupiv.models.erp_connection import ERPConnection
from rupiv.revenue_recognition.journal import JournalEntry


# ---------------------------------------------------------------------------
# Formatter unit tests
# ---------------------------------------------------------------------------

SAMPLE_ENTRIES = [
    JournalEntry(
        date=date(2026, 3, 1),
        debit_account="1200-AR",
        credit_account="4000-saas-revenue",
        amount=Decimal("5000.00"),
        currency="EUR",
        description="Revenue recognition — over_time — 2026-03",
        reference_type="revenue_schedule_entry",
        reference_id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
    ),
    JournalEntry(
        date=date(2026, 3, 1),
        debit_account="1200-AR",
        credit_account="4010-outcome-revenue",
        amount=Decimal("1500.50"),
        currency="EUR",
        description="Revenue recognition — point_in_time — 2026-03",
        reference_type="revenue_schedule_entry",
        reference_id=uuid.UUID("22222222-3333-4444-5555-666666666666"),
    ),
]

GL_MAPPING = {
    "1200-AR": "1100",
    "4000-saas-revenue": "4100",
    "4010-outcome-revenue": "4200",
}


class TestCSVFormatter:
    """Tests for generic CSV export."""

    def test_csv_output_has_header_and_rows(self) -> None:
        result = to_csv(SAMPLE_ENTRIES)
        lines = result.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "date,debit_account,credit_account,amount,currency" in lines[0]

    def test_csv_with_gl_mapping(self) -> None:
        result = to_csv(SAMPLE_ENTRIES, gl_mapping=GL_MAPPING)
        assert "1100" in result  # mapped from 1200-AR
        assert "4100" in result  # mapped from 4000-saas-revenue
        assert "1200-AR" not in result  # original replaced

    def test_csv_without_mapping_uses_original(self) -> None:
        result = to_csv(SAMPLE_ENTRIES)
        assert "1200-AR" in result
        assert "4000-saas-revenue" in result

    def test_empty_entries(self) -> None:
        result = to_csv([])
        lines = result.strip().split("\n")
        assert len(lines) == 1  # header only


class TestQuickBooksIIFFormatter:
    """Tests for QuickBooks IIF export."""

    def test_iif_has_header_and_entries(self) -> None:
        result = to_quickbooks_iif(SAMPLE_ENTRIES)
        assert "!TRNS" in result
        assert "!SPL" in result
        assert "ENDTRNS" in result

    def test_iif_has_debit_and_credit_lines(self) -> None:
        result = to_quickbooks_iif(SAMPLE_ENTRIES)
        lines = result.strip().split("\n")
        trns_lines = [l for l in lines if l.startswith("TRNS\t")]
        spl_lines = [l for l in lines if l.startswith("SPL\t")]
        assert len(trns_lines) == 2
        assert len(spl_lines) == 2

    def test_iif_with_gl_mapping(self) -> None:
        result = to_quickbooks_iif(SAMPLE_ENTRIES, gl_mapping=GL_MAPPING)
        assert "1100" in result
        assert "1200-AR" not in result


class TestXeroCSVFormatter:
    """Tests for Xero CSV export."""

    def test_xero_has_header_and_paired_rows(self) -> None:
        result = to_xero_csv(SAMPLE_ENTRIES)
        lines = result.strip().split("\n")
        assert len(lines) == 5  # header + 2*2 rows

    def test_xero_with_gl_mapping(self) -> None:
        result = to_xero_csv(SAMPLE_ENTRIES, gl_mapping=GL_MAPPING)
        assert "4200" in result  # mapped from 4010-outcome-revenue


class TestFormatEntries:
    """Tests for the format_entries dispatcher."""

    def test_dispatches_csv(self) -> None:
        result = format_entries("csv", SAMPLE_ENTRIES)
        assert "date,debit_account" in result

    def test_dispatches_quickbooks(self) -> None:
        result = format_entries("quickbooks", SAMPLE_ENTRIES)
        assert "!TRNS" in result

    def test_dispatches_xero(self) -> None:
        result = format_entries("xero", SAMPLE_ENTRIES)
        assert "*Narration" in result

    def test_unsupported_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported ERP provider"):
            format_entries("sap", SAMPLE_ENTRIES)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestERPConnectionAPI:
    """Tests for ERP connection CRUD endpoints."""

    async def test_create_connection(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/v1/erp/connections",
            json={"provider": "csv", "name": "Test CSV Export"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "csv"
        assert data["name"] == "Test CSV Export"
        assert data["is_active"] is True

    async def test_list_connections(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        conn = ERPConnection(provider="xero", name="Xero Prod", is_active=True)
        db_session.add(conn)
        await db_session.commit()

        resp = await client.get("/v1/erp/connections")
        assert resp.status_code == 200
        connections = resp.json()
        assert len(connections) >= 1

    async def test_update_connection(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        conn = ERPConnection(provider="csv", name="Old Name", is_active=True)
        db_session.add(conn)
        await db_session.commit()
        await db_session.refresh(conn)

        resp = await client.patch(
            f"/v1/erp/connections/{conn.id}",
            json={
                "name": "New Name",
                "gl_account_mapping": {"1200-AR": "1100"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["gl_account_mapping"]["1200-AR"] == "1100"
