"""Double-entry ledger for Agent-to-Agent (A2A) fund transfers.

Backed by PostgreSQL via the ``ledger_entries`` table. Each function
manages its own database session so callers (including LangGraph agent
nodes) don't need to pass one in.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import structlog
from sqlalchemy import func, select, update

from rupiv.db import _get_session_factory
from rupiv.models.ledger import EntryType, LedgerEntry, LedgerStatus

log = structlog.get_logger(__name__)


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    """Coerce a string to UUID if needed.

    If the string is not a valid UUID, generate a deterministic UUID5
    from it so that the same string always maps to the same account.
    """
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, value)


# Re-export for backward compatibility with callers that do
# ``from rupiv.billing.ledger import EntryStatus, LedgerEntry``
EntryStatus = LedgerStatus  # alias


# ---------------------------------------------------------------------------
# DTO for public API (callers don't deal with ORM objects)
# ---------------------------------------------------------------------------


@dataclass
class LedgerEntryDTO:
    """Serialisable snapshot of a ledger entry."""

    entry_id: str
    transaction_id: str
    account_id: str
    entry_type: EntryType
    amount: Decimal
    currency: str
    description: str
    status: LedgerStatus
    created_at: datetime


def _to_dto(entry: LedgerEntry) -> LedgerEntryDTO:
    """Convert an ORM ``LedgerEntry`` to a DTO."""
    return LedgerEntryDTO(
        entry_id=str(entry.id),
        transaction_id=str(entry.transaction_id),
        account_id=str(entry.account_id),
        entry_type=entry.entry_type,
        amount=Decimal(str(entry.amount)),
        currency=entry.currency,
        description=entry.description or "",
        status=entry.status,
        created_at=entry.created_at,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_transfer(
    from_account: str,
    to_account: str,
    amount: Decimal,
    currency: str,
    description: str,
) -> str:
    """Create a matched debit + credit pair.

    Returns the ``transaction_id`` shared by both entries.
    """
    if amount <= 0:
        msg = "Transfer amount must be positive"
        raise ValueError(msg)

    transaction_id = uuid.uuid4()

    debit = LedgerEntry(
        transaction_id=transaction_id,
        account_id=_to_uuid(from_account),
        entry_type=EntryType.DEBIT,
        amount=amount,
        currency=currency,
        description=description,
        status=LedgerStatus.PENDING,
    )
    credit = LedgerEntry(
        transaction_id=transaction_id,
        account_id=_to_uuid(to_account),
        entry_type=EntryType.CREDIT,
        amount=amount,
        currency=currency,
        description=description,
        status=LedgerStatus.PENDING,
    )

    session_factory = _get_session_factory()
    async with session_factory() as session:
        session.add(debit)
        session.add(credit)
        await session.commit()

    log.info(
        "ledger.transfer_created",
        transaction_id=str(transaction_id),
        from_account=from_account,
        to_account=to_account,
        amount=str(amount),
        currency=currency,
    )
    return str(transaction_id)


async def get_balance(account_id: str) -> Decimal:
    """Return the settled balance for *account_id*.

    Balance = sum(credits) - sum(debits) where status = settled.
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        credit_result = await session.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.account_id == _to_uuid(account_id),
                LedgerEntry.entry_type == EntryType.CREDIT,
                LedgerEntry.status == LedgerStatus.SETTLED,
            ),
        )
        credits = Decimal(str(credit_result.scalar_one()))

        debit_result = await session.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.account_id == _to_uuid(account_id),
                LedgerEntry.entry_type == EntryType.DEBIT,
                LedgerEntry.status == LedgerStatus.SETTLED,
            ),
        )
        debits = Decimal(str(debit_result.scalar_one()))

    balance = credits - debits
    log.debug("ledger.balance", account_id=account_id, balance=str(balance))
    return balance


async def settle_transaction(transaction_id: str) -> None:
    """Mark all entries belonging to *transaction_id* as settled."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(LedgerEntry).where(LedgerEntry.transaction_id == _to_uuid(transaction_id)),
        )
        entries = list(result.scalars().all())

        if not entries:
            msg = f"Transaction {transaction_id} not found"
            raise ValueError(msg)

        debit_total = sum(
            (Decimal(str(e.amount)) for e in entries if e.entry_type == EntryType.DEBIT),
            Decimal("0"),
        )
        credit_total = sum(
            (Decimal(str(e.amount)) for e in entries if e.entry_type == EntryType.CREDIT),
            Decimal("0"),
        )
        if debit_total != credit_total:
            msg = f"Imbalanced transaction {transaction_id}: debit={debit_total}, credit={credit_total}"
            raise ValueError(msg)

        await session.execute(
            update(LedgerEntry)
            .where(LedgerEntry.transaction_id == _to_uuid(transaction_id))
            .values(status=LedgerStatus.SETTLED),
        )
        await session.commit()

    log.info("ledger.transaction_settled", transaction_id=transaction_id)


async def fail_transaction(transaction_id: str) -> None:
    """Mark all entries belonging to *transaction_id* as failed."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(LedgerEntry).where(LedgerEntry.transaction_id == _to_uuid(transaction_id)),
        )
        entries = list(result.scalars().all())

        if not entries:
            msg = f"Transaction {transaction_id} not found"
            raise ValueError(msg)

        await session.execute(
            update(LedgerEntry)
            .where(LedgerEntry.transaction_id == _to_uuid(transaction_id))
            .values(status=LedgerStatus.FAILED),
        )
        await session.commit()

    log.info("ledger.transaction_failed", transaction_id=transaction_id)


async def get_entries_by_transaction(transaction_id: str) -> list[LedgerEntryDTO]:
    """Return all entries for a given *transaction_id*."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(LedgerEntry).where(LedgerEntry.transaction_id == _to_uuid(transaction_id)),
        )
        return [_to_dto(e) for e in result.scalars().all()]


async def get_entries_by_account(account_id: str) -> list[LedgerEntryDTO]:
    """Return all entries for a given *account_id*, newest first."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(LedgerEntry)
            .where(LedgerEntry.account_id == _to_uuid(account_id))
            .order_by(LedgerEntry.created_at.desc()),
        )
        return [_to_dto(e) for e in result.scalars().all()]


async def get_recent_entries(limit: int = 50) -> list[LedgerEntryDTO]:
    """Return the most recent ledger entries across all accounts."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(LedgerEntry)
            .order_by(LedgerEntry.created_at.desc())
            .limit(limit),
        )
        return [_to_dto(e) for e in result.scalars().all()]


async def get_available_balance(account_id: str) -> Decimal:
    """Return the available balance for *account_id*.

    Available = settled balance minus pending debits.
    """
    settled = await get_balance(account_id)

    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.account_id == _to_uuid(account_id),
                LedgerEntry.entry_type == EntryType.DEBIT,
                LedgerEntry.status == LedgerStatus.PENDING,
            ),
        )
        pending_debits = Decimal(str(result.scalar_one()))

    available = settled - pending_debits
    log.debug(
        "ledger.available_balance",
        account_id=account_id,
        settled=str(settled),
        pending_debits=str(pending_debits),
        available=str(available),
    )
    return available
