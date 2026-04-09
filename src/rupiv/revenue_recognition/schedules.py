"""Revenue schedule generation (IFRS 15 Step 5).

Creates month-by-month schedule entries that show how much revenue is
recognised vs deferred for each performance obligation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import structlog

from rupiv.revenue_recognition.obligations import PerformanceObligation

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# GL account constants
# ---------------------------------------------------------------------------

GL_AR = "1200-AR"
GL_SAAS_REVENUE = "4000-saas-revenue"
GL_OUTCOME_REVENUE = "4010-outcome-revenue"
GL_DEFERRED_REVENUE = "4800-deferred-revenue"

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RevenueScheduleEntry:
    """One month's revenue recognition entry for a single obligation."""

    period: str  # "YYYY-MM"
    obligation_id: uuid.UUID
    method: str  # "over_time" | "point_in_time"
    gross_amount: Decimal
    recognized: Decimal
    deferred: Decimal
    gl_debit: str
    gl_credit: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FOUR_PLACES = Decimal("0.0001")


def _months_between(start: date, end: date) -> list[str]:
    """Return a sorted list of ``YYYY-MM`` strings from *start* to *end* inclusive."""
    periods: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        periods.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return periods


def _credit_account(obligation: PerformanceObligation) -> str:
    """Choose the appropriate revenue GL credit account."""
    if obligation.obligation_type == "outcome_delivery":
        return GL_OUTCOME_REVENUE
    return GL_SAAS_REVENUE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_schedule(
    obligation: PerformanceObligation,
    total_allocated: Decimal,
    start: date,
    end: date,
) -> list[RevenueScheduleEntry]:
    """Generate a revenue schedule for one performance obligation.

    Parameters
    ----------
    obligation:
        The obligation whose revenue is being scheduled.
    total_allocated:
        Amount allocated to this obligation (from ``allocate_transaction_price``).
    start / end:
        The period over which revenue should be recognised.

    Returns
    -------
    list[RevenueScheduleEntry]
        Monthly entries.  For ``over_time`` obligations the total is spread
        evenly across months.  For ``point_in_time`` obligations the full
        amount is recognised in the month of *start* (the event date).
    """
    credit_account = _credit_account(obligation)

    # ---- point_in_time: recognise everything in the event month ----------
    if obligation.recognition_method == "point_in_time":
        period = f"{start.year:04d}-{start.month:02d}"
        entry = RevenueScheduleEntry(
            period=period,
            obligation_id=obligation.id,
            method="point_in_time",
            gross_amount=total_allocated,
            recognized=total_allocated,
            deferred=Decimal("0"),
            gl_debit=GL_AR,
            gl_credit=credit_account,
        )
        log.debug(
            "schedule_point_in_time",
            obligation_id=str(obligation.id),
            period=period,
            amount=str(total_allocated),
        )
        return [entry]

    # ---- over_time: spread evenly across months --------------------------
    periods = _months_between(start, end)
    num_periods = len(periods)
    if num_periods == 0:
        return []

    monthly_amount = (total_allocated / Decimal(num_periods)).quantize(
        _FOUR_PLACES, rounding=ROUND_HALF_UP,
    )

    entries: list[RevenueScheduleEntry] = []
    recognized_so_far = Decimal("0")
    remaining = total_allocated

    for idx, period in enumerate(periods):
        if idx == num_periods - 1:
            # Last month absorbs rounding residual.
            recognized = remaining
        else:
            recognized = monthly_amount
            remaining -= recognized

        recognized_so_far += recognized
        deferred = total_allocated - recognized_so_far

        entry = RevenueScheduleEntry(
            period=period,
            obligation_id=obligation.id,
            method="over_time",
            gross_amount=total_allocated,
            recognized=recognized,
            deferred=deferred,
            gl_debit=GL_AR,
            gl_credit=credit_account,
        )
        entries.append(entry)

    log.debug(
        "schedule_over_time",
        obligation_id=str(obligation.id),
        num_periods=num_periods,
        monthly=str(monthly_amount),
    )

    return entries
