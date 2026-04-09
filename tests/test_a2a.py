"""Tests for the A2A agent-to-agent SEPA payment flow.

Tests cover intent validation, insufficient balance handling, ledger
reservation, settlement, and graph compilation.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from rupiv.agents.a2a_agent import (
    A2AState,
    a2a_graph,
    compliance_check,
    execute_transfer,
    initiate_a2a_payment,
    register_agent_account,
    reserve_funds,
    set_policy_rules,
    settle,
    validate_intent,
    _agent_accounts,
)
from rupiv.billing.adyen_client import AdyenTransfer
from rupiv.billing.ledger import (
    EntryStatus,
    EntryType,
    _entries,
    create_transfer,
    get_balance,
    get_entries_by_transaction,
    settle_transaction,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_state() -> None:
    """Clear in-memory ledger and agent accounts before each test."""
    _entries.clear()
    _agent_accounts.clear()


@pytest.fixture()
def buyer_id() -> str:
    return "buyer-agent-001"


@pytest.fixture()
def seller_id() -> str:
    return "seller-agent-001"


@pytest.fixture()
def registered_agents(buyer_id: str, seller_id: str) -> None:
    """Register both buyer and seller agent accounts."""
    register_agent_account(buyer_id, iban="NL91ABNA0417164300", bic="ABNANL2A")
    register_agent_account(seller_id, iban="DE89370400440532013000", bic="COBADEFFXXX")


@pytest.fixture()
def base_state(buyer_id: str, seller_id: str) -> A2AState:
    """Return a minimal valid A2AState for testing individual nodes."""
    return A2AState(
        intent_id="test-intent-001",
        buyer_agent_id=buyer_id,
        seller_agent_id=seller_id,
        amount="25.00",
        currency="EUR",
        reason="data enrichment",
        seller_iban=None,
        seller_bic=None,
        compliance_passed=None,
        ledger_transaction_id=None,
        ledger_debit_id=None,
        ledger_credit_id=None,
        transfer_id=None,
        psp_reference=None,
        settlement_status=None,
        error=None,
        messages=[],
    )


# ---------------------------------------------------------------------------
# test_a2a_validate_intent
# ---------------------------------------------------------------------------


class TestValidateIntent:
    """Tests for the validate_intent node."""

    async def test_valid_intent_passes(
        self, base_state: A2AState, registered_agents: None
    ) -> None:
        """A valid intent with registered agents passes validation."""
        result = await validate_intent(base_state)

        assert result.get("error") is None
        assert result.get("seller_iban") == "DE89370400440532013000"
        assert result.get("seller_bic") == "COBADEFFXXX"
        assert any("validated" in str(m.get("content", "")) for m in result.get("messages", []))

    async def test_zero_amount_rejected(
        self, base_state: A2AState, registered_agents: None
    ) -> None:
        """An amount of zero is rejected."""
        base_state["amount"] = "0"
        result = await validate_intent(base_state)
        assert result.get("error") == "Amount must be positive"

    async def test_negative_amount_rejected(
        self, base_state: A2AState, registered_agents: None
    ) -> None:
        """A negative amount is rejected."""
        base_state["amount"] = "-10.00"
        result = await validate_intent(base_state)
        assert result.get("error") == "Amount must be positive"

    async def test_invalid_amount_format(
        self, base_state: A2AState, registered_agents: None
    ) -> None:
        """A non-numeric amount is rejected."""
        base_state["amount"] = "not-a-number"
        result = await validate_intent(base_state)
        assert result.get("error") == "Invalid amount format"

    async def test_same_buyer_seller_rejected(
        self, base_state: A2AState, buyer_id: str
    ) -> None:
        """Buyer and seller cannot be the same agent."""
        register_agent_account(buyer_id, iban="NL91ABNA0417164300")
        base_state["seller_agent_id"] = buyer_id
        result = await validate_intent(base_state)
        assert result.get("error") == "Buyer and seller cannot be the same agent"

    async def test_unknown_buyer_rejected(
        self, base_state: A2AState, seller_id: str
    ) -> None:
        """An unregistered buyer agent is rejected."""
        register_agent_account(seller_id, iban="DE89370400440532013000")
        result = await validate_intent(base_state)
        assert "not found" in (result.get("error") or "")

    async def test_unsupported_currency_rejected(
        self, base_state: A2AState, registered_agents: None
    ) -> None:
        """A non-EUR currency is rejected for A2A MVP."""
        base_state["currency"] = "USD"
        result = await validate_intent(base_state)
        assert "not supported" in (result.get("error") or "")


# ---------------------------------------------------------------------------
# test_a2a_insufficient_balance
# ---------------------------------------------------------------------------


class TestInsufficientBalance:
    """Tests for reserve_funds when balance is insufficient."""

    async def test_buyer_with_zero_balance_rejected(
        self, base_state: A2AState, registered_agents: None
    ) -> None:
        """A buyer with zero balance cannot reserve funds."""
        result = await reserve_funds(base_state)
        assert result.get("error") is not None
        assert "Insufficient balance" in result["error"]

    async def test_buyer_with_low_balance_rejected(
        self,
        base_state: A2AState,
        buyer_id: str,
        seller_id: str,
        registered_agents: None,
    ) -> None:
        """A buyer whose balance is less than the amount is rejected."""
        # Give buyer a settled balance of 10 EUR
        tx = await create_transfer(
            from_account="external-funding",
            to_account=buyer_id,
            amount=Decimal("10.00"),
            currency="EUR",
            description="Initial funding",
        )
        await settle_transaction(tx)

        # Try to send 25 EUR
        base_state["amount"] = "25.00"
        result = await reserve_funds(base_state)
        assert result.get("error") is not None
        assert "Insufficient balance" in result["error"]


# ---------------------------------------------------------------------------
# test_a2a_ledger_reserve
# ---------------------------------------------------------------------------


class TestLedgerReserve:
    """Tests for reserve_funds creating ledger entries."""

    async def test_debit_entry_created_with_pending_status(
        self,
        base_state: A2AState,
        buyer_id: str,
        seller_id: str,
        registered_agents: None,
    ) -> None:
        """reserve_funds creates a pending debit+credit pair."""
        # Fund the buyer first
        funding_tx = await create_transfer(
            from_account="external-funding",
            to_account=buyer_id,
            amount=Decimal("100.00"),
            currency="EUR",
            description="Initial funding",
        )
        await settle_transaction(funding_tx)

        result = await reserve_funds(base_state)

        assert result.get("error") is None
        assert result.get("ledger_transaction_id") is not None
        assert result.get("ledger_debit_id") is not None
        assert result.get("ledger_credit_id") is not None

        # Verify the entries are PENDING
        entries = await get_entries_by_transaction(result["ledger_transaction_id"])
        assert len(entries) == 2

        debit_entries = [e for e in entries if e.entry_type == EntryType.DEBIT]
        credit_entries = [e for e in entries if e.entry_type == EntryType.CREDIT]

        assert len(debit_entries) == 1
        assert len(credit_entries) == 1

        assert debit_entries[0].account_id == buyer_id
        assert debit_entries[0].amount == Decimal("25.00")
        assert debit_entries[0].status == EntryStatus.PENDING

        assert credit_entries[0].account_id == seller_id
        assert credit_entries[0].amount == Decimal("25.00")
        assert credit_entries[0].status == EntryStatus.PENDING


# ---------------------------------------------------------------------------
# test_a2a_settle_transaction
# ---------------------------------------------------------------------------


class TestSettleTransaction:
    """Tests for the settle node finalising ledger entries."""

    async def test_entries_move_to_settled(
        self,
        base_state: A2AState,
        buyer_id: str,
        seller_id: str,
        registered_agents: None,
    ) -> None:
        """After settle, both debit and credit entries are SETTLED."""
        # Fund buyer and create reservation
        funding_tx = await create_transfer(
            from_account="external-funding",
            to_account=buyer_id,
            amount=Decimal("100.00"),
            currency="EUR",
            description="Initial funding",
        )
        await settle_transaction(funding_tx)

        reserve_result = await reserve_funds(base_state)
        tx_id = reserve_result["ledger_transaction_id"]

        # Build state as it would be after execute_transfer succeeded
        settle_state = dict(base_state)
        settle_state["ledger_transaction_id"] = tx_id
        settle_state["ledger_debit_id"] = reserve_result["ledger_debit_id"]
        settle_state["ledger_credit_id"] = reserve_result["ledger_credit_id"]
        settle_state["transfer_id"] = "PSP-TEST-123"
        settle_state["psp_reference"] = "PSP-TEST-123"

        result = await settle(settle_state)  # type: ignore[arg-type]

        assert result.get("error") is None
        assert result["settlement_status"] == "settled"

        # Verify entries are settled
        entries = await get_entries_by_transaction(tx_id)
        assert all(e.status == EntryStatus.SETTLED for e in entries)

        # Verify balances
        buyer_balance = await get_balance(buyer_id)
        seller_balance = await get_balance(seller_id)
        assert buyer_balance == Decimal("75.00")  # 100 - 25
        assert seller_balance == Decimal("25.00")

    async def test_settle_reverses_on_error(
        self,
        base_state: A2AState,
        buyer_id: str,
        registered_agents: None,
    ) -> None:
        """If error is set, settle reverses the reservation."""
        # Fund and reserve
        funding_tx = await create_transfer(
            from_account="external-funding",
            to_account=buyer_id,
            amount=Decimal("100.00"),
            currency="EUR",
            description="Initial funding",
        )
        await settle_transaction(funding_tx)

        reserve_result = await reserve_funds(base_state)
        tx_id = reserve_result["ledger_transaction_id"]

        # Simulate an error from execute_transfer
        error_state = dict(base_state)
        error_state["ledger_transaction_id"] = tx_id
        error_state["error"] = "Transfer refused by Adyen"

        result = await settle(error_state)  # type: ignore[arg-type]

        assert result["settlement_status"] == "failed"

        # Verify entries are failed (reversed)
        entries = await get_entries_by_transaction(tx_id)
        assert all(e.status == EntryStatus.FAILED for e in entries)


# ---------------------------------------------------------------------------
# test_a2a_graph_compiles
# ---------------------------------------------------------------------------


class TestGraphCompilation:
    """Tests that the LangGraph graph compiles correctly."""

    def test_graph_compiles(self) -> None:
        """The A2A settlement graph should compile without error."""
        assert a2a_graph is not None
        # The graph should have the expected nodes
        node_names = set(a2a_graph.nodes.keys())
        expected_nodes = {
            "validate_intent",
            "compliance_check",
            "reserve_funds",
            "execute_transfer",
            "settle",
        }
        assert expected_nodes.issubset(node_names), (
            f"Missing nodes: {expected_nodes - node_names}"
        )

    async def test_full_graph_with_mocked_adyen(
        self,
        buyer_id: str,
        seller_id: str,
        registered_agents: None,
    ) -> None:
        """Full graph execution with a mocked Adyen client succeeds."""
        # Fund the buyer
        funding_tx = await create_transfer(
            from_account="external-funding",
            to_account=buyer_id,
            amount=Decimal("500.00"),
            currency="EUR",
            description="Initial funding",
        )
        await settle_transaction(funding_tx)

        mock_transfer = AdyenTransfer(
            psp_reference="PSP-MOCK-12345",
            status="Authorised",
            amount=Decimal("25.00"),
            currency="EUR",
            reference="test-ref",
        )

        with patch(
            "rupiv.agents.a2a_agent.get_adyen_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.create_sepa_transfer.return_value = mock_transfer
            mock_get_client.return_value = mock_client

            result = await initiate_a2a_payment(
                buyer_agent_id=buyer_id,
                seller_agent_id=seller_id,
                amount="25.00",
                currency="EUR",
                reason="test payment",
            )

        assert result.get("error") is None
        assert result["settlement_status"] == "settled"
        assert result.get("psp_reference") == "PSP-MOCK-12345"

        # Verify final balances
        buyer_balance = await get_balance(buyer_id)
        seller_balance = await get_balance(seller_id)
        assert buyer_balance == Decimal("475.00")
        assert seller_balance == Decimal("25.00")
