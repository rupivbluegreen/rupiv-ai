"""Tests for rupiv.entities.intercompany — intercompany invoicing."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.entities.intercompany import generate_intercompany_invoice
from rupiv.models.entity import EntityType, LegalEntity


class TestIntercompanyInvoice:
    """Tests for generate_intercompany_invoice."""

    async def test_intercompany_invoice_same_hierarchy(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Two entities under the same root should produce an invoice."""
        # Create root entity
        root_id = uuid.uuid4()
        root = LegalEntity(
            id=root_id,
            name="AcmeAI Holding BV",
            entity_type=EntityType.BV,
            country_code="NL",
            vat_number="NL123456789B01",
            default_currency="EUR",
            parent_id=None,
            is_active=True,
        )
        db_session.add(root)

        # Create two children under root
        child_a_id = uuid.uuid4()
        child_a = LegalEntity(
            id=child_a_id,
            name="AcmeAI GmbH",
            entity_type=EntityType.GMBH,
            country_code="DE",
            vat_number="DE123456789",
            default_currency="EUR",
            parent_id=root_id,
            is_active=True,
        )
        db_session.add(child_a)

        child_b_id = uuid.uuid4()
        child_b = LegalEntity(
            id=child_b_id,
            name="AcmeAI SAS",
            entity_type=EntityType.SAS,
            country_code="FR",
            vat_number="FR12345678901",
            default_currency="EUR",
            parent_id=root_id,
            is_active=True,
        )
        db_session.add(child_b)
        await db_session.flush()

        invoice = await generate_intercompany_invoice(
            session=db_session,
            from_entity_id=child_a_id,
            to_entity_id=child_b_id,
            amount=Decimal("5000.00"),
            description="Infrastructure services Q1 2026",
            currency="EUR",
        )

        assert invoice is not None
        assert invoice.subtotal == Decimal("5000.00")
        assert invoice.total == Decimal("5000.00")
        assert invoice.currency == "EUR"
        assert invoice.invoice_number.startswith("IC-DE-FR-")

    async def test_intercompany_invoice_different_roots(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Entities in different hierarchies should raise ValueError."""
        # Create two independent root entities (different trees)
        root_a_id = uuid.uuid4()
        root_a = LegalEntity(
            id=root_a_id,
            name="AcmeAI BV",
            entity_type=EntityType.BV,
            country_code="NL",
            default_currency="EUR",
            parent_id=None,
            is_active=True,
        )
        db_session.add(root_a)

        root_b_id = uuid.uuid4()
        root_b = LegalEntity(
            id=root_b_id,
            name="OtherCorp GmbH",
            entity_type=EntityType.GMBH,
            country_code="DE",
            default_currency="EUR",
            parent_id=None,
            is_active=True,
        )
        db_session.add(root_b)
        await db_session.flush()

        with pytest.raises(ValueError, match="not in the same hierarchy"):
            await generate_intercompany_invoice(
                session=db_session,
                from_entity_id=root_a_id,
                to_entity_id=root_b_id,
                amount=Decimal("1000.00"),
                description="Should fail",
            )
