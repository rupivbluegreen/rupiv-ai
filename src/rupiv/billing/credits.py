"""Credit operations — atomic balance management for credit-based billing.

ALL money arithmetic uses ``decimal.Decimal`` — never ``float``.
"""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.credit import CreditBalance, CreditTransaction, TransactionType

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class InsufficientCreditsError(Exception):
    """Raised when a customer tries to consume more credits than available."""

    def __init__(self, available: Decimal, requested: Decimal) -> None:
        self.available = available
        self.requested = requested
        super().__init__(f"Insufficient credits: available={available}, requested={requested}")


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


async def get_or_create_balance(
    session: AsyncSession,
    customer_id: str | __import__('uuid').UUID,
    currency: str = "EUR",
) -> CreditBalance:
    """Return the credit balance for *customer_id*, creating one if absent.

    Uses the session transaction — caller is responsible for commit.
    """
    import uuid as _uuid

    cid = _uuid.UUID(str(customer_id)) if not isinstance(customer_id, _uuid.UUID) else customer_id

    result = await session.execute(select(CreditBalance).where(CreditBalance.customer_id == cid))
    balance = result.scalar_one_or_none()

    if balance is None:
        balance = CreditBalance(
            customer_id=cid,
            balance=Decimal("0.0000"),
            currency=currency,
        )
        session.add(balance)
        await session.flush()
        log.info("credits.balance_created", customer_id=str(cid), currency=currency)

    return balance


async def purchase_credits(
    session: AsyncSession,
    customer_id: str | __import__('uuid').UUID,
    amount: Decimal,
    description: str,
    invoice_id: str | __import__('uuid').UUID | None = None,
) -> CreditTransaction:
    """Add credits to a customer's balance.

    Returns the created ``CreditTransaction``.
    """
    import uuid as _uuid

    cid = _uuid.UUID(str(customer_id)) if not isinstance(customer_id, _uuid.UUID) else customer_id
    inv_id = _uuid.UUID(str(invoice_id)) if invoice_id is not None else None

    balance = await get_or_create_balance(session, cid)
    balance.balance = Decimal(str(balance.balance)) + amount

    txn = CreditTransaction(
        customer_id=cid,
        credit_balance_id=balance.id,
        transaction_type=TransactionType.PURCHASE,
        amount=amount,
        description=description,
        reference_type="invoice" if inv_id else None,
        reference_id=inv_id,
    )
    session.add(txn)
    await session.flush()

    log.info(
        "credits.purchased",
        customer_id=str(cid),
        amount=str(amount),
        new_balance=str(balance.balance),
    )
    return txn


async def consume_credits(
    session: AsyncSession,
    customer_id: str | __import__('uuid').UUID,
    amount: Decimal,
    description: str,
    event_id: str | __import__('uuid').UUID | None = None,
) -> CreditTransaction:
    """Deduct credits from a customer's balance.

    Raises ``InsufficientCreditsError`` if balance < *amount*.
    The check and deduction happen within the same session transaction.
    """
    import uuid as _uuid

    cid = _uuid.UUID(str(customer_id)) if not isinstance(customer_id, _uuid.UUID) else customer_id
    ev_id = _uuid.UUID(str(event_id)) if event_id is not None else None

    balance = await get_or_create_balance(session, cid)
    current = Decimal(str(balance.balance))

    if current < amount:
        raise InsufficientCreditsError(available=current, requested=amount)

    balance.balance = current - amount

    txn = CreditTransaction(
        customer_id=cid,
        credit_balance_id=balance.id,
        transaction_type=TransactionType.CONSUMPTION,
        amount=-amount,
        description=description,
        reference_type="event" if ev_id else None,
        reference_id=ev_id,
    )
    session.add(txn)
    await session.flush()

    log.info(
        "credits.consumed",
        customer_id=str(cid),
        amount=str(amount),
        new_balance=str(balance.balance),
    )
    return txn


async def get_balance(
    session: AsyncSession,
    customer_id: str | __import__('uuid').UUID,
) -> Decimal:
    """Return the current credit balance for *customer_id*.

    Returns ``Decimal("0")`` if no balance record exists.
    """
    import uuid as _uuid

    cid = _uuid.UUID(str(customer_id)) if not isinstance(customer_id, _uuid.UUID) else customer_id

    result = await session.execute(
        select(CreditBalance.balance).where(CreditBalance.customer_id == cid),
    )
    raw = result.scalar_one_or_none()
    return Decimal(str(raw)) if raw is not None else Decimal("0")


async def get_transactions(
    session: AsyncSession,
    customer_id: str | __import__('uuid').UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[CreditTransaction]:
    """Return credit transactions for *customer_id*, newest first."""
    import uuid as _uuid

    cid = _uuid.UUID(str(customer_id)) if not isinstance(customer_id, _uuid.UUID) else customer_id

    result = await session.execute(
        select(CreditTransaction)
        .where(CreditTransaction.customer_id == cid)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
        .offset(offset),
    )
    return list(result.scalars().all())


async def refund_credits(
    session: AsyncSession,
    customer_id: str | __import__('uuid').UUID,
    amount: Decimal,
    description: str,
) -> CreditTransaction:
    """Refund (add back) credits to a customer's balance."""
    import uuid as _uuid

    cid = _uuid.UUID(str(customer_id)) if not isinstance(customer_id, _uuid.UUID) else customer_id

    balance = await get_or_create_balance(session, cid)
    balance.balance = Decimal(str(balance.balance)) + amount

    txn = CreditTransaction(
        customer_id=cid,
        credit_balance_id=balance.id,
        transaction_type=TransactionType.REFUND,
        amount=amount,
        description=description,
    )
    session.add(txn)
    await session.flush()

    log.info(
        "credits.refunded",
        customer_id=str(cid),
        amount=str(amount),
        new_balance=str(balance.balance),
    )
    return txn
