"""Tests for the double-entry ledger in rupiv.billing.ledger."""

from __future__ import annotations

from decimal import Decimal

import pytest

from rupiv.billing.ledger import (
    EntryStatus,
    _entries,
    create_transfer,
    get_balance,
    settle_transaction,
)


@pytest.fixture(autouse=True)
def _clear_ledger() -> None:
    """Clear the in-memory ledger store before each test."""
    _entries.clear()


# ---------------------------------------------------------------------------
# create_transfer
# ---------------------------------------------------------------------------


async def test_create_transfer() -> None:
    """create_transfer produces matching debit + credit entries."""
    tx_id = await create_transfer(
        from_account="acct-buyer",
        to_account="acct-seller",
        amount=Decimal("25.00"),
        currency="EUR",
        description="Data enrichment payment",
    )

    assert tx_id  # non-empty string

    # Should have exactly 2 entries with the same transaction_id
    entries = [e for e in _entries if e.transaction_id == tx_id]
    assert len(entries) == 2

    debit = [e for e in entries if e.entry_type.value == "debit"]
    credit = [e for e in entries if e.entry_type.value == "credit"]
    assert len(debit) == 1
    assert len(credit) == 1

    assert debit[0].account_id == "acct-buyer"
    assert debit[0].amount == Decimal("25.00")
    assert debit[0].status == EntryStatus.PENDING

    assert credit[0].account_id == "acct-seller"
    assert credit[0].amount == Decimal("25.00")
    assert credit[0].status == EntryStatus.PENDING


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------


async def test_get_balance_empty() -> None:
    """A new account with no entries has a balance of 0."""
    balance = await get_balance("acct-nonexistent")
    assert balance == Decimal("0")


async def test_get_balance_after_settled_transfer() -> None:
    """After settling a transfer, the balance reflects credits and debits."""
    tx_id = await create_transfer(
        from_account="acct-a",
        to_account="acct-b",
        amount=Decimal("50.00"),
        currency="EUR",
        description="Test transfer",
    )
    await settle_transaction(tx_id)

    # acct-b received a credit -> positive balance
    balance_b = await get_balance("acct-b")
    assert balance_b == Decimal("50.00")

    # acct-a was debited -> negative balance
    balance_a = await get_balance("acct-a")
    assert balance_a == Decimal("-50.00")


# ---------------------------------------------------------------------------
# settle_transaction
# ---------------------------------------------------------------------------


async def test_settle_transaction() -> None:
    """settle_transaction moves entries from pending to settled."""
    tx_id = await create_transfer(
        from_account="acct-x",
        to_account="acct-y",
        amount=Decimal("10.00"),
        currency="EUR",
        description="Settlement test",
    )

    # Before settlement: all pending
    entries_before = [e for e in _entries if e.transaction_id == tx_id]
    assert all(e.status == EntryStatus.PENDING for e in entries_before)

    await settle_transaction(tx_id)

    # After settlement: all settled
    entries_after = [e for e in _entries if e.transaction_id == tx_id]
    assert all(e.status == EntryStatus.SETTLED for e in entries_after)
