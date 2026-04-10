"""Tests for the double-entry ledger backed by PostgreSQL."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from rupiv.billing.ledger import (
    EntryStatus,
    create_transfer,
    get_balance,
    get_entries_by_transaction,
    settle_transaction,
)


@pytest.fixture(autouse=True)
def _patch_session_factory(db_engine: AsyncEngine) -> Any:
    """Patch _get_session_factory so the ledger uses the test DB engine."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("rupiv.billing.ledger._get_session_factory", return_value=factory):
        yield


# ---------------------------------------------------------------------------
# create_transfer
# ---------------------------------------------------------------------------


async def test_create_transfer() -> None:
    """create_transfer produces matching debit + credit entries."""
    tx_id = await create_transfer(
        from_account="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        to_account="11111111-2222-3333-4444-555555555555",
        amount=Decimal("25.00"),
        currency="EUR",
        description="Data enrichment payment",
    )

    assert tx_id  # non-empty string

    entries = await get_entries_by_transaction(tx_id)
    assert len(entries) == 2

    debit = [e for e in entries if e.entry_type.value == "debit"]
    credit = [e for e in entries if e.entry_type.value == "credit"]
    assert len(debit) == 1
    assert len(credit) == 1

    assert debit[0].amount == Decimal("25.00")
    assert debit[0].status == EntryStatus.PENDING

    assert credit[0].amount == Decimal("25.00")
    assert credit[0].status == EntryStatus.PENDING


async def test_create_transfer_negative_amount() -> None:
    """create_transfer rejects non-positive amounts."""
    with pytest.raises(ValueError, match="positive"):
        await create_transfer(
            from_account="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            to_account="11111111-2222-3333-4444-555555555555",
            amount=Decimal("-10.00"),
            currency="EUR",
            description="bad",
        )


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------


async def test_get_balance_empty() -> None:
    """A new account with no entries has a balance of 0."""
    balance = await get_balance("aaaaaaaa-bbbb-cccc-dddd-ffffffffffff")
    assert balance == Decimal("0")


async def test_get_balance_after_settled_transfer() -> None:
    """After settling a transfer, the balance reflects credits and debits."""
    acct_a = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    acct_b = "11111111-2222-3333-4444-555555555555"

    tx_id = await create_transfer(
        from_account=acct_a,
        to_account=acct_b,
        amount=Decimal("50.00"),
        currency="EUR",
        description="Test transfer",
    )
    await settle_transaction(tx_id)

    balance_b = await get_balance(acct_b)
    assert balance_b == Decimal("50.00")

    balance_a = await get_balance(acct_a)
    assert balance_a == Decimal("-50.00")


# ---------------------------------------------------------------------------
# settle_transaction
# ---------------------------------------------------------------------------


async def test_settle_transaction() -> None:
    """settle_transaction moves entries from pending to settled."""
    acct_x = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    acct_y = "11111111-2222-3333-4444-555555555555"

    tx_id = await create_transfer(
        from_account=acct_x,
        to_account=acct_y,
        amount=Decimal("10.00"),
        currency="EUR",
        description="Settlement test",
    )

    # Before settlement: all pending
    entries_before = await get_entries_by_transaction(tx_id)
    assert all(e.status == EntryStatus.PENDING for e in entries_before)

    await settle_transaction(tx_id)

    # After settlement: all settled
    entries_after = await get_entries_by_transaction(tx_id)
    assert all(e.status == EntryStatus.SETTLED for e in entries_after)
