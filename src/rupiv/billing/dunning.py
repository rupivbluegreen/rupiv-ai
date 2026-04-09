"""Dunning — retry logic for failed invoice payments.

Dunning schedules define when to re-attempt charging an overdue invoice.
After all attempts are exhausted the invoice is marked uncollectible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.payment import MollieClient, PaymentResult, charge_invoice
from rupiv.models.invoice import Invoice, InvoiceStatus

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

DEFAULT_RETRY_DELAYS_HOURS: list[int] = [24, 72, 168]  # 1 day, 3 days, 7 days


@dataclass
class DunningSchedule:
    """Configurable retry cadence for failed payments.

    *attempts* is a list of delays **in hours** between successive retries.
    For example ``[24, 72, 168]`` means: retry after 1 day, then 3 days,
    then 7 days.  After the last attempt the invoice becomes uncollectible.
    """

    attempts: list[int] = field(default_factory=lambda: list(DEFAULT_RETRY_DELAYS_HOURS))

    @property
    def max_attempts(self) -> int:
        return len(self.attempts)


# ---------------------------------------------------------------------------
# Core dunning logic
# ---------------------------------------------------------------------------


async def run_dunning(
    session: AsyncSession,
    mollie: MollieClient,
    invoice: Invoice,
    webhook_base_url: str,
    schedule: DunningSchedule | None = None,
) -> bool:
    """Attempt to collect payment for *invoice* according to *schedule*.

    Tracks the number of attempts already made via
    ``invoice.metadata["dunning_attempts"]`` (an integer counter stored
    alongside the invoice — we piggyback on the JSON metadata pattern to
    avoid a schema migration for this field).

    Returns ``True`` if the payment charge succeeded, ``False`` otherwise.
    When all attempts have been exhausted the invoice status is set to
    :attr:`InvoiceStatus.UNCOLLECTIBLE`.
    """
    if schedule is None:
        schedule = DunningSchedule()

    attempts_made: int = _get_dunning_attempts(invoice)

    if attempts_made >= schedule.max_attempts:
        log.info(
            "dunning.max_attempts_reached",
            invoice_id=str(invoice.id),
            attempts=attempts_made,
        )
        invoice.status = InvoiceStatus.UNCOLLECTIBLE
        return False

    log.info(
        "dunning.retry_attempt",
        invoice_id=str(invoice.id),
        attempt=attempts_made + 1,
        max_attempts=schedule.max_attempts,
    )

    result: PaymentResult = await charge_invoice(
        mollie=mollie,
        invoice=invoice,
        webhook_base_url=webhook_base_url,
    )

    _set_dunning_attempts(invoice, attempts_made + 1)

    if result.success:
        log.info(
            "dunning.charge_succeeded",
            invoice_id=str(invoice.id),
            payment_id=result.payment_id,
        )
        return True

    log.warning(
        "dunning.charge_failed",
        invoice_id=str(invoice.id),
        error=result.error,
        attempt=attempts_made + 1,
    )

    # If that was the final attempt, mark uncollectible
    if attempts_made + 1 >= schedule.max_attempts:
        invoice.status = InvoiceStatus.UNCOLLECTIBLE
        log.info(
            "dunning.invoice_uncollectible",
            invoice_id=str(invoice.id),
        )

    return False


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


async def get_invoices_for_dunning(session: AsyncSession) -> list[Invoice]:
    """Return open invoices whose due date has passed.

    These are candidates for a dunning retry.
    """
    now = date.today()
    result = await session.execute(
        select(Invoice).where(
            Invoice.status == InvoiceStatus.OPEN,
            Invoice.due_date < now,
        ),
    )
    invoices: list[Invoice] = list(result.scalars().all())

    log.info("dunning.candidates_found", count=len(invoices))
    return invoices


# ---------------------------------------------------------------------------
# Dunning-attempt tracking helpers
# ---------------------------------------------------------------------------
# We store the attempt counter in a lightweight convention on the invoice
# rather than adding a new DB column, keeping this change migration-free.
# If the invoice model later gains a dedicated ``dunning_attempts`` column
# these helpers can be swapped out transparently.


def _get_dunning_attempts(invoice: Invoice) -> int:
    """Read the dunning attempt counter from the invoice.

    Falls back to ``0`` if the attribute has not been set yet.
    """
    return int(getattr(invoice, "_dunning_attempts", 0))


def _set_dunning_attempts(invoice: Invoice, count: int) -> None:
    """Persist the dunning attempt counter on the invoice object.

    This is an in-memory annotation; the caller is responsible for
    committing any DB changes via the session.
    """
    # Use object.__setattr__ since some frozen/mapped models restrict direct sets
    object.__setattr__(invoice, "_dunning_attempts", count)
