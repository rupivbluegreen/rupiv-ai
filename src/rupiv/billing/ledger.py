"""Double-entry ledger for Agent-to-Agent (A2A) fund transfers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class EntryType(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class EntryStatus(str, Enum):
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"


@dataclass
class LedgerEntry:
    """A single debit or credit entry."""

    entry_id: str
    transaction_id: str
    account_id: str
    entry_type: EntryType
    amount: Decimal
    currency: str
    description: str
    status: EntryStatus
    created_at: datetime


# ---------------------------------------------------------------------------
# In-memory store (replace with PostgreSQL in production)
# ---------------------------------------------------------------------------

_entries: list[LedgerEntry] = []

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

    Every transfer produces exactly **two** ledger entries so that the
    books always balance.

    Args:
        from_account: Account to debit.
        to_account: Account to credit.
        amount: Transfer amount (must be > 0).
        currency: ISO-4217 currency code.
        description: Human-readable memo.

    Returns:
        The ``transaction_id`` shared by both entries.

    Raises:
        ValueError: If *amount* is not positive.
    """
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")

    transaction_id = str(uuid4())
    now = datetime.now(UTC)

    debit = LedgerEntry(
        entry_id=str(uuid4()),
        transaction_id=transaction_id,
        account_id=from_account,
        entry_type=EntryType.DEBIT,
        amount=amount,
        currency=currency,
        description=description,
        status=EntryStatus.PENDING,
        created_at=now,
    )
    credit = LedgerEntry(
        entry_id=str(uuid4()),
        transaction_id=transaction_id,
        account_id=to_account,
        entry_type=EntryType.CREDIT,
        amount=amount,
        currency=currency,
        description=description,
        status=EntryStatus.PENDING,
        created_at=now,
    )

    _entries.extend([debit, credit])

    log.info(
        "ledger.transfer_created",
        transaction_id=transaction_id,
        from_account=from_account,
        to_account=to_account,
        amount=str(amount),
        currency=currency,
    )
    return transaction_id


async def get_balance(account_id: str) -> Decimal:
    """Return the settled balance for *account_id*.

    Balance = sum(credits) - sum(debits) where status = settled.
    """
    credits = sum(
        (
            e.amount
            for e in _entries
            if e.account_id == account_id
            and e.entry_type == EntryType.CREDIT
            and e.status == EntryStatus.SETTLED
        ),
        Decimal("0"),
    )
    debits = sum(
        (
            e.amount
            for e in _entries
            if e.account_id == account_id
            and e.entry_type == EntryType.DEBIT
            and e.status == EntryStatus.SETTLED
        ),
        Decimal("0"),
    )

    balance = credits - debits
    log.debug("ledger.balance", account_id=account_id, balance=str(balance))
    return balance


async def settle_transaction(transaction_id: str) -> None:
    """Mark all entries belonging to *transaction_id* as settled.

    Raises:
        ValueError: If the transaction is not found or entries are not
            balanced (safety check).
    """
    entries = [e for e in _entries if e.transaction_id == transaction_id]

    if not entries:
        raise ValueError(f"Transaction {transaction_id} not found")

    # Safety: verify matching debit + credit
    debit_total = sum(
        (e.amount for e in entries if e.entry_type == EntryType.DEBIT),
        Decimal("0"),
    )
    credit_total = sum(
        (e.amount for e in entries if e.entry_type == EntryType.CREDIT),
        Decimal("0"),
    )
    if debit_total != credit_total:
        raise ValueError(
            f"Imbalanced transaction {transaction_id}: debit={debit_total}, credit={credit_total}",
        )

    for entry in entries:
        entry.status = EntryStatus.SETTLED

    log.info("ledger.transaction_settled", transaction_id=transaction_id)


async def fail_transaction(transaction_id: str) -> None:
    """Mark all entries belonging to *transaction_id* as failed.

    Used when a payment is refused or reversed.

    Raises:
        ValueError: If the transaction is not found.
    """
    entries = [e for e in _entries if e.transaction_id == transaction_id]

    if not entries:
        raise ValueError(f"Transaction {transaction_id} not found")

    for entry in entries:
        entry.status = EntryStatus.FAILED

    log.info("ledger.transaction_failed", transaction_id=transaction_id)


async def get_entries_by_transaction(transaction_id: str) -> list[LedgerEntry]:
    """Return all entries for a given *transaction_id*."""
    return [e for e in _entries if e.transaction_id == transaction_id]


async def get_entries_by_account(account_id: str) -> list[LedgerEntry]:
    """Return all entries for a given *account_id*, newest first."""
    entries = [e for e in _entries if e.account_id == account_id]
    return sorted(entries, key=lambda e: e.created_at, reverse=True)


async def get_recent_entries(limit: int = 50) -> list[LedgerEntry]:
    """Return the most recent ledger entries across all accounts."""
    sorted_entries = sorted(_entries, key=lambda e: e.created_at, reverse=True)
    return sorted_entries[:limit]


async def get_available_balance(account_id: str) -> Decimal:
    """Return the available balance for *account_id*.

    Available = settled balance minus pending debits.  This is the amount
    that can be reserved for new transfers.
    """
    settled = await get_balance(account_id)

    pending_debits = sum(
        (
            e.amount
            for e in _entries
            if e.account_id == account_id
            and e.entry_type == EntryType.DEBIT
            and e.status == EntryStatus.PENDING
        ),
        Decimal("0"),
    )

    available = settled - pending_debits
    log.debug(
        "ledger.available_balance",
        account_id=account_id,
        settled=str(settled),
        pending_debits=str(pending_debits),
        available=str(available),
    )
    return available
