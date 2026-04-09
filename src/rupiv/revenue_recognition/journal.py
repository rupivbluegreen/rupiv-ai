"""GL journal entry generation from revenue schedule entries.

Converts each :class:`RevenueScheduleEntry` into a double-entry
:class:`JournalEntry` suitable for export to an external GL / ERP.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import structlog

from rupiv.revenue_recognition.schedules import RevenueScheduleEntry

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JournalEntry:
    """A single GL journal entry (one debit, one credit)."""

    date: date
    debit_account: str
    credit_account: str
    amount: Decimal
    currency: str
    description: str
    reference_type: str
    reference_id: uuid.UUID = field(default_factory=uuid.uuid4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_journal_entries(
    schedule_entries: list[RevenueScheduleEntry],
    currency: str = "EUR",
) -> list[JournalEntry]:
    """Convert schedule entries into GL journal entries.

    For each schedule entry:
    - If revenue is **recognised** (``recognized > 0``): debit AR, credit the
      revenue account.
    - If revenue is **deferred** (``deferred > 0`` and this is the first
      period): a separate deferral entry is not generated because the schedule
      already separates recognised from deferred amounts.  The journal entry
      reflects only the recognised portion for the period.

    Parameters
    ----------
    schedule_entries:
        Output from :func:`generate_schedule`.
    currency:
        ISO 4217 currency code (default ``"EUR"``).

    Returns
    -------
    list[JournalEntry]
    """
    entries: list[JournalEntry] = []

    for se in schedule_entries:
        if se.recognized <= 0:
            continue

        je = JournalEntry(
            date=date.fromisoformat(f"{se.period}-01"),
            debit_account=se.gl_debit,
            credit_account=se.gl_credit,
            amount=se.recognized,
            currency=currency,
            description=f"Revenue recognition — {se.method} — {se.period}",
            reference_type="revenue_schedule_entry",
            reference_id=se.obligation_id,
        )
        entries.append(je)

    log.debug("journal_entries_generated", count=len(entries))
    return entries
