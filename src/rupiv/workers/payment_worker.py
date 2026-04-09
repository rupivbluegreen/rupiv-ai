"""Payment execution worker — picks up open invoices and processes payment.

Run as a standalone process::

    python -m rupiv.workers.payment_worker
"""

from __future__ import annotations

import asyncio
import json
import signal
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.billing.payment import PaymentMethod, PaymentResult, charge_invoice
from rupiv.config import get_settings
from rupiv.db import _get_session_factory
from rupiv.models.invoice import Invoice, InvoiceStatus

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

PAYMENT_QUEUE_KEY = "rupiv:payments:queue"
POLL_INTERVAL_SECONDS: int = 30


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

async def process_invoice_payment(
    session: AsyncSession,
    invoice: Invoice,
) -> bool:
    """Attempt to charge a single open invoice.

    Flow:
    1. Load the invoice and customer.
    2. Resolve the payment method (stubbed for MVP).
    3. Call ``charge_invoice`` from the billing.payment module.
    4. Update invoice status to ``paid`` or ``uncollectible`` based on result.

    Args:
        session: Active database session.
        invoice: The Invoice ORM object to charge.

    Returns:
        ``True`` if the payment succeeded.
    """
    invoice_id = str(invoice.id)
    total = Decimal(str(invoice.total))

    log.info(
        "payment_worker.processing",
        invoice_id=invoice_id,
        total=str(total),
        currency=invoice.currency,
    )

    # Build a domain-compatible invoice object for the charge_invoice stub.
    # The billing.payment module uses getattr, so a simple namespace works.
    class _InvoiceProxy:
        def __init__(self, inv: Invoice) -> None:
            self.invoice_id = str(inv.id)
            self.total = Decimal(str(inv.total))
            self.currency = inv.currency

    invoice_proxy = _InvoiceProxy(invoice)

    # TODO: Resolve real payment method from customer's stored methods.
    # For MVP we use a stub payment method.
    payment_method = PaymentMethod(
        method_id=f"pm_{invoice.customer_id}",
        provider="mollie",
        type="ideal",
    )

    try:
        result: PaymentResult = await charge_invoice(invoice_proxy, payment_method)
    except Exception:
        log.error(
            "payment_worker.charge_exception",
            invoice_id=invoice_id,
            exc_info=True,
        )
        return False

    if result.success:
        await session.execute(
            update(Invoice)
            .where(Invoice.id == invoice.id)
            .values(
                status=InvoiceStatus.PAID,
                paid_at=datetime.now(timezone.utc),
                mollie_payment_id=result.payment_id,
            )
        )
        log.info(
            "payment_worker.payment_succeeded",
            invoice_id=invoice_id,
            payment_id=result.payment_id,
        )
        return True
    else:
        await session.execute(
            update(Invoice)
            .where(Invoice.id == invoice.id)
            .values(status=InvoiceStatus.UNCOLLECTIBLE)
        )
        log.error(
            "payment_worker.payment_failed",
            invoice_id=invoice_id,
            error=result.error,
        )
        return False


async def process_open_invoices(session: AsyncSession) -> tuple[int, int]:
    """Find all invoices with status=open and attempt payment.

    Returns:
        Tuple of ``(succeeded_count, failed_count)``.
    """
    stmt = (
        select(Invoice)
        .where(Invoice.status == InvoiceStatus.OPEN)
        .options(selectinload(Invoice.customer))
        .order_by(Invoice.created_at.asc())
    )
    result = await session.execute(stmt)
    invoices: list[Invoice] = list(result.scalars().all())

    if not invoices:
        return 0, 0

    log.info("payment_worker.open_invoices_found", count=len(invoices))

    succeeded = 0
    failed = 0

    for invoice in invoices:
        try:
            ok = await process_invoice_payment(session, invoice)
            if ok:
                succeeded += 1
            else:
                failed += 1
        except Exception:
            log.error(
                "payment_worker.invoice_error",
                invoice_id=str(invoice.id),
                exc_info=True,
            )
            failed += 1

    return succeeded, failed


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

class PaymentWorker:
    """Async worker that processes open invoices for payment.

    Operates in two modes:
    - Polls the database on a fixed interval for open invoices.
    - Picks up specific invoice IDs from a Redis list (``rupiv:payments:queue``)
      for immediate processing.
    """

    def __init__(self) -> None:
        self._shutdown: bool = False

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        sig_name = signal.Signals(sig).name
        log.info("payment_worker.signal_received", signal=sig_name)
        self._shutdown = True

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    async def run(self) -> None:
        """Run the payment worker loop."""
        import redis.asyncio as aioredis

        self._install_signal_handlers()
        settings = get_settings()

        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.REDIS_URL,
            decode_responses=True,
        )
        session_factory = _get_session_factory()

        log.info(
            "payment_worker.started",
            queue=PAYMENT_QUEUE_KEY,
            poll_interval=POLL_INTERVAL_SECONDS,
        )

        last_poll = 0.0

        try:
            while not self._shutdown:
                # Check Redis queue for specific invoice IDs to process
                try:
                    result = await redis_client.blpop(
                        PAYMENT_QUEUE_KEY,
                        timeout=1,
                    )
                except Exception:
                    log.error("payment_worker.redis_blpop_failed", exc_info=True)
                    await asyncio.sleep(1)
                    result = None

                if result is not None:
                    _key, raw_payload = result
                    try:
                        payload = json.loads(raw_payload)
                        invoice_id = payload.get("invoice_id") if isinstance(payload, dict) else raw_payload
                    except (json.JSONDecodeError, TypeError):
                        invoice_id = raw_payload

                    async with session_factory() as session:
                        try:
                            stmt = select(Invoice).where(Invoice.id == invoice_id)
                            res = await session.execute(stmt)
                            invoice = res.scalar_one_or_none()
                            if invoice and invoice.status == InvoiceStatus.OPEN:
                                await process_invoice_payment(session, invoice)
                                await session.commit()
                            elif invoice:
                                log.info(
                                    "payment_worker.skip_non_open",
                                    invoice_id=str(invoice_id),
                                    status=invoice.status.value,
                                )
                            else:
                                log.warning(
                                    "payment_worker.invoice_not_found",
                                    invoice_id=str(invoice_id),
                                )
                        except Exception:
                            await session.rollback()
                            log.error(
                                "payment_worker.queued_payment_failed",
                                invoice_id=str(invoice_id),
                                exc_info=True,
                            )

                # Periodic poll for any open invoices
                elapsed = asyncio.get_event_loop().time() - last_poll
                if elapsed >= POLL_INTERVAL_SECONDS:
                    async with session_factory() as session:
                        try:
                            succeeded, failed = await process_open_invoices(session)
                            await session.commit()
                            if succeeded or failed:
                                log.info(
                                    "payment_worker.poll_complete",
                                    succeeded=succeeded,
                                    failed=failed,
                                )
                        except Exception:
                            await session.rollback()
                            log.error("payment_worker.poll_failed", exc_info=True)

                    last_poll = asyncio.get_event_loop().time()

        finally:
            await redis_client.aclose()
            log.info("payment_worker.shutdown_complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for ``python -m rupiv.workers.payment_worker``."""
    log.info("payment_worker.starting")
    worker = PaymentWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        log.info("payment_worker.interrupted")


if __name__ == "__main__":
    main()
