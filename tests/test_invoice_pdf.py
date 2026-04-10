"""Tests for PDF invoice generation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.invoicing.pdf import generate_invoice_pdf
from rupiv.models.customer import Customer
from rupiv.models.invoice import Invoice, InvoiceLineItem


CUSTOMER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
INVOICE_ID = uuid.UUID("22222222-3333-4444-5555-666666666666")


@pytest.fixture
async def invoice_with_lines(db_session: AsyncSession) -> Invoice:
    """Seed a customer and invoice with line items."""
    customer = Customer(
        id=CUSTOMER_ID,
        name="PDF Test Corp",
        email="pdf@test.example.com",
        external_id="ext-pdf-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
        vat_number="NL123456789B01",
    )
    db_session.add(customer)

    now = datetime.now(UTC)
    invoice = Invoice(
        id=INVOICE_ID,
        customer_id=CUSTOMER_ID,
        subscription_id=uuid.uuid4(),
        invoice_number="INV-2026-PDF-001",
        status="open",
        currency="EUR",
        subtotal="4950.0000",
        tax_amount="1039.5000",
        total="5989.5000",
        tax_rate="0.2100",
        period_start=now - timedelta(days=30),
        period_end=now,
        due_date=(now + timedelta(days=14)).date(),
    )
    db_session.add(invoice)

    li1 = InvoiceLineItem(
        id=uuid.uuid4(),
        invoice_id=INVOICE_ID,
        description="Resolved support tickets (Mar 2026)",
        metric="ticket_resolved",
        quantity="5000.0000",
        unit_amount="0.9900",
        amount="4950.0000",
    )
    db_session.add(li1)

    await db_session.commit()

    # Re-fetch with line items loaded
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    result = await db_session.execute(
        select(Invoice)
        .where(Invoice.id == INVOICE_ID)
        .options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.customer),
        ),
    )
    return result.scalar_one()


class TestGenerateInvoicePDF:
    """Tests for the PDF generation function."""

    async def test_returns_bytes(self, invoice_with_lines: Invoice) -> None:
        result = generate_invoice_pdf(invoice_with_lines)
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 100  # non-trivial PDF

    async def test_pdf_starts_with_header(self, invoice_with_lines: Invoice) -> None:
        result = generate_invoice_pdf(invoice_with_lines)
        assert bytes(result)[:5] == b"%PDF-"

    async def test_pdf_has_substantial_size(self, invoice_with_lines: Invoice) -> None:
        result = generate_invoice_pdf(invoice_with_lines)
        # A real invoice PDF with line items should be > 1KB
        assert len(bytes(result)) > 1000


class TestInvoicePDFEndpoint:
    """Tests for the /invoices/{id}/pdf endpoint."""

    async def test_download_pdf(
        self, client: AsyncClient, invoice_with_lines: Invoice,
    ) -> None:
        resp = await client.get(f"/v1/invoices/{INVOICE_ID}/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:5] == b"%PDF-"

    async def test_not_found(self, client: AsyncClient) -> None:
        resp = await client.get(f"/v1/invoices/{uuid.uuid4()}/pdf")
        assert resp.status_code == 404
