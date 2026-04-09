"""Intercompany billing — generate invoices between entities in the same hierarchy."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.entities.hierarchy import EntityTree
from rupiv.models.entity import LegalEntity
from rupiv.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


async def generate_intercompany_invoice(
    session: AsyncSession,
    from_entity_id: uuid.UUID,
    to_entity_id: uuid.UUID,
    amount: Decimal,
    description: str,
    currency: str = "EUR",
) -> Invoice:
    """Create an invoice between two entities in the same corporate hierarchy.

    Args:
        session: Async database session.
        from_entity_id: The entity issuing the invoice (seller).
        to_entity_id: The entity receiving the invoice (buyer).
        amount: Invoice amount.
        description: Line item description.
        currency: ISO 4217 currency code.

    Returns:
        The created Invoice.

    Raises:
        ValueError: If either entity does not exist or they are not in the
                    same corporate hierarchy.
    """
    # Load both entities
    from_result = await session.execute(
        select(LegalEntity).where(LegalEntity.id == from_entity_id)
    )
    from_entity: LegalEntity | None = from_result.scalar_one_or_none()
    if from_entity is None:
        raise ValueError(f"Entity {from_entity_id} not found")

    to_result = await session.execute(
        select(LegalEntity).where(LegalEntity.id == to_entity_id)
    )
    to_entity: LegalEntity | None = to_result.scalar_one_or_none()
    if to_entity is None:
        raise ValueError(f"Entity {to_entity_id} not found")

    # Validate both entities share the same root (same hierarchy)
    from_root = await EntityTree.get_root(session, from_entity_id)
    to_root = await EntityTree.get_root(session, to_entity_id)

    if from_root is None or to_root is None or from_root.id != to_root.id:
        raise ValueError(
            f"Entities {from_entity_id} and {to_entity_id} are not in the same hierarchy"
        )

    now = datetime.now(tz=timezone.utc)

    # Generate a unique intercompany invoice number
    invoice_number = f"IC-{from_entity.country_code}-{to_entity.country_code}-{uuid.uuid4().hex[:8].upper()}"

    invoice = Invoice(
        customer_id=to_entity_id,
        subscription_id=from_entity_id,  # Re-use subscription_id field for from_entity
        invoice_number=invoice_number,
        status=InvoiceStatus.DRAFT,
        subtotal=amount,
        tax_amount=Decimal("0"),
        total=amount,
        currency=currency.upper(),
        period_start=now,
        period_end=now,
        due_date=(now + timedelta(days=30)).date(),
    )
    session.add(invoice)
    await session.flush()

    line_item = InvoiceLineItem(
        invoice_id=invoice.id,
        description=description,
        quantity=Decimal("1"),
        unit_amount=amount,
        amount=amount,
        pricing_model="intercompany",
    )
    session.add(line_item)
    await session.flush()
    await session.refresh(invoice)

    logger.info(
        "intercompany_invoice_generated",
        invoice_id=str(invoice.id),
        invoice_number=invoice_number,
        from_entity_id=str(from_entity_id),
        to_entity_id=str(to_entity_id),
        amount=str(amount),
        currency=currency,
    )

    return invoice
