"""Transaction price allocation (IFRS 15 Step 4).

Allocates the total transaction price to each performance obligation based on
their relative standalone selling prices.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import structlog

from rupiv.revenue_recognition.obligations import PerformanceObligation

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllocationResult:
    """The portion of the transaction price allocated to one obligation."""

    obligation_id: uuid.UUID
    allocated_amount: Decimal
    allocation_pct: Decimal


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_FOUR_PLACES = Decimal("0.0001")
_PCT_PLACES = Decimal("0.000001")


def allocate_transaction_price(
    total_price: Decimal,
    obligations: list[PerformanceObligation],
) -> list[AllocationResult]:
    """Allocate *total_price* to obligations by relative standalone selling price.

    If the sum of standalone selling prices equals ``total_price`` the
    allocation is a simple pass-through.  Otherwise each obligation receives
    a share proportional to its standalone selling price relative to the
    total of all standalone selling prices.

    Parameters
    ----------
    total_price:
        The overall transaction price to distribute.
    obligations:
        Performance obligations with standalone selling prices.

    Returns
    -------
    list[AllocationResult]
        One result per obligation. The sum of ``allocated_amount`` equals
        ``total_price`` (any rounding residual is added to the last entry).
    """
    if not obligations:
        return []

    ssp_total = sum(ob.standalone_selling_price for ob in obligations)

    results: list[AllocationResult] = []
    allocated_so_far = Decimal("0")

    for idx, ob in enumerate(obligations):
        if ssp_total == 0:
            # Edge case: all SSPs are zero — split evenly.
            pct = Decimal("1") / Decimal(len(obligations))
        else:
            pct = ob.standalone_selling_price / ssp_total

        pct = pct.quantize(_PCT_PLACES, rounding=ROUND_HALF_UP)

        if idx == len(obligations) - 1:
            # Last obligation absorbs rounding residual.
            amount = total_price - allocated_so_far
        else:
            amount = (total_price * pct).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)
            allocated_so_far += amount

        result = AllocationResult(
            obligation_id=ob.id,
            allocated_amount=amount,
            allocation_pct=pct,
        )
        results.append(result)
        log.debug(
            "price_allocated",
            obligation_id=str(ob.id),
            amount=str(amount),
            pct=str(pct),
        )

    return results
