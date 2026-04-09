"""Contract management — renewal checks, early termination, and queries."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.contract import (
    Contract,
    ContractRenewalType,
    ContractStatus,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


def check_renewal_due(contract: Contract) -> bool:
    """Check if a contract is due for renewal.

    A contract is due for renewal when it is within 30 days of its end date
    and has renewal_type = AUTO.

    Args:
        contract: The contract to check.

    Returns:
        True if renewal is due, False otherwise.
    """
    if contract.renewal_type != ContractRenewalType.AUTO:
        return False

    if contract.status != ContractStatus.ACTIVE:
        return False

    today = date.today()
    days_until_end = (contract.end_date - today).days
    return 0 <= days_until_end <= 30


async def renew_contract(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> Contract:
    """Create a new contract for the next term.

    Marks the current contract as completed and creates a successor.

    Args:
        session: Async database session.
        contract_id: The contract to renew.

    Returns:
        The new Contract for the next term.

    Raises:
        ValueError: If contract is not found or not active.
    """
    result = await session.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if contract is None:
        raise ValueError(f"Contract {contract_id} not found")

    if contract.status != ContractStatus.ACTIVE:
        raise ValueError(f"Cannot renew contract in status {contract.status.value}")

    # Complete the current contract
    contract.status = ContractStatus.COMPLETED
    contract.auto_renewed = True

    # Create the successor
    new_start = contract.end_date
    new_end = new_start + relativedelta(months=contract.term_months)
    new_contract = Contract(
        quote_id=contract.quote_id,
        subscription_id=contract.subscription_id,
        start_date=new_start,
        end_date=new_end,
        term_months=contract.term_months,
        renewal_type=contract.renewal_type,
        early_termination_pct=contract.early_termination_pct,
        status=ContractStatus.ACTIVE,
    )
    session.add(new_contract)
    await session.flush()
    await session.refresh(new_contract)

    logger.info(
        "contract_renewed",
        old_contract_id=str(contract_id),
        new_contract_id=str(new_contract.id),
        new_start=str(new_start),
        new_end=str(new_end),
    )

    return new_contract


def calculate_early_termination_fee(
    contract: Contract,
    cancellation_date: date,
    monthly_value: Decimal | None = None,
) -> Decimal:
    """Calculate the early termination fee for a contract.

    Fee = remaining_months * monthly_value * early_termination_pct / 100

    Args:
        contract: The contract being terminated.
        cancellation_date: Date of cancellation.
        monthly_value: Monthly value of the contract. If None, uses
                       the quote's estimated_monthly (if available) or 0.

    Returns:
        The early termination fee as a Decimal.
    """
    if cancellation_date >= contract.end_date:
        return Decimal("0")

    # Calculate remaining months (round up partial months)
    remaining_days = (contract.end_date - cancellation_date).days
    remaining_months = Decimal(str(remaining_days)) / Decimal("30")
    # Round up to nearest whole month
    remaining_months = remaining_months.quantize(Decimal("1"), rounding="ROUND_UP")

    if monthly_value is None:
        # Try to get from the associated quote
        if contract.quote and hasattr(contract.quote, "estimated_monthly"):
            monthly_value = Decimal(str(contract.quote.estimated_monthly))
        else:
            monthly_value = Decimal("0")

    termination_pct = Decimal(str(contract.early_termination_pct)) / Decimal("100")
    fee = remaining_months * monthly_value * termination_pct

    return fee


async def get_active_contract(
    session: AsyncSession,
    subscription_id: uuid.UUID,
) -> Contract | None:
    """Get the active contract for a subscription.

    Args:
        session: Async database session.
        subscription_id: The subscription to look up.

    Returns:
        The active Contract, or None if none exists.
    """
    result = await session.execute(
        select(Contract).where(
            Contract.subscription_id == subscription_id,
            Contract.status == ContractStatus.ACTIVE,
        ),
    )
    return result.scalar_one_or_none()
