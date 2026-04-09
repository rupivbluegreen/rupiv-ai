"""Payment execution worker — charges invoices via Mollie."""

from __future__ import annotations

from typing import Any

import structlog

from rupiv.billing.payment import PaymentMethod, charge_invoice

log = structlog.get_logger(__name__)


async def process_payment(invoice_id: str) -> bool:
    """Load the invoice, charge via Mollie, and update status.

    Args:
        invoice_id: The ID of the invoice to charge.

    Returns:
        ``True`` if the payment succeeded, ``False`` otherwise.

    High-level flow:
    1. Load the invoice and associated payment method from PostgreSQL.
    2. Call the Mollie charge stub.
    3. Update the invoice status to ``"paid"`` or ``"payment_failed"``.
    """
    log.info("worker.payment.start", invoice_id=invoice_id)

    # TODO: Replace with actual DB query
    # async with get_db_session() as session:
    #     invoice = await session.get(Invoice, invoice_id)
    #     payment_method_record = await session.get(
    #         PaymentMethodRecord, invoice.payment_method_id
    #     )

    invoice: Any = None  # stub
    if invoice is None:
        log.error("worker.payment.invoice_not_found", invoice_id=invoice_id)
        return False

    # TODO: Fetch real payment method from DB
    payment_method = PaymentMethod(
        method_id="pm_stub",
        provider="mollie",
        type="ideal",
    )

    result = await charge_invoice(invoice, payment_method)

    if result.success:
        # TODO: Update invoice status in DB
        # invoice.status = "paid"
        # invoice.payment_id = result.payment_id
        # await session.commit()
        log.info(
            "worker.payment.success",
            invoice_id=invoice_id,
            payment_id=result.payment_id,
        )
        return True
    else:
        # TODO: Update invoice status in DB
        # invoice.status = "payment_failed"
        # await session.commit()
        log.error(
            "worker.payment.failed",
            invoice_id=invoice_id,
            error=result.error,
        )
        return False
