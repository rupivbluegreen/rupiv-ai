"""LangGraph agent-to-agent (A2A) SEPA settlement agent.

Stub implementation for post-MVP.  Orchestrates autonomous payments
between AI agents via SEPA fiat rails (Adyen EU), with compliance
checks and double-entry ledger bookkeeping.
"""

from __future__ import annotations

import uuid as _uuid_mod
from decimal import Decimal
from typing import Any, Literal, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class A2AState(TypedDict):
    """State that flows through the A2A settlement graph."""

    intent_id: str
    buyer_agent_id: str
    seller_agent_id: str
    amount: str  # Decimal as string
    currency: str
    reason: str
    compliance_passed: bool | None
    ledger_debit_id: str | None
    ledger_credit_id: str | None
    transfer_id: str | None  # SEPA transfer reference
    settlement_status: str | None  # "pending" | "settled" | "failed"
    error: str | None
    messages: list


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def validate_intent(state: A2AState) -> dict[str, Any]:
    """Check that both agents exist and the amount is valid.

    TODO: Query the agent registry to verify buyer and seller exist,
    are active, and have valid payment credentials.
    """
    log.info(
        "a2a_agent.validate_intent",
        intent_id=state["intent_id"],
        buyer=state["buyer_agent_id"],
        seller=state["seller_agent_id"],
        amount=state["amount"],
    )

    try:
        amount = Decimal(state.get("amount", "0"))
    except Exception:
        return {"error": "Invalid amount format"}

    if amount <= Decimal("0"):
        return {"error": "Amount must be positive"}

    if not state.get("buyer_agent_id"):
        return {"error": "Buyer agent ID is required"}

    if not state.get("seller_agent_id"):
        return {"error": "Seller agent ID is required"}

    if state["buyer_agent_id"] == state["seller_agent_id"]:
        return {"error": "Buyer and seller cannot be the same agent"}

    # TODO: Verify both agent IDs exist in the agents table
    # TODO: Check buyer has sufficient balance or credit line
    # TODO: Validate currency is supported for A2A (EUR only for MVP)

    log.info("a2a_agent.intent_valid", intent_id=state["intent_id"])
    return {
        "messages": state.get("messages", [])
        + [{"role": "system", "content": "A2A intent validated"}],
    }


async def compliance_check(state: A2AState) -> dict[str, Any]:
    """Run the compliance agent for this A2A transaction.

    TODO: Invoke the compliance graph and check the result.  For now
    this is a pass-through stub.
    """
    if state.get("error"):
        return {}

    log.info(
        "a2a_agent.compliance_check",
        intent_id=state["intent_id"],
        amount=state["amount"],
        currency=state["currency"],
    )

    # TODO: Invoke compliance_graph from compliance_agent.py
    # result = await check_compliance(
    #     transaction_type="a2a_payment",
    #     customer_id=state["buyer_agent_id"],
    #     amount=state["amount"],
    #     currency=state["currency"],
    # )
    # if not result.get("is_compliant"):
    #     return {"error": "Compliance check failed", "compliance_passed": False}

    log.info("a2a_agent.compliance_passed", intent_id=state["intent_id"])
    return {"compliance_passed": True}


async def reserve_funds(state: A2AState) -> dict[str, Any]:
    """Create a debit ledger entry for the buyer.

    TODO: Insert a ``LedgerEntry`` with ``entry_type=DEBIT`` and
    ``status=PENDING``.  This reserves the funds from the buyer's
    account balance.
    """
    if state.get("error"):
        return {}

    log.info(
        "a2a_agent.reserve_funds",
        intent_id=state["intent_id"],
        buyer=state["buyer_agent_id"],
        amount=state["amount"],
    )

    # TODO: Create actual ledger entry via rupiv.billing.ledger
    # transaction_id = uuid.uuid4()
    # debit_entry = LedgerEntry(
    #     transaction_id=transaction_id,
    #     account_id=state["buyer_agent_id"],
    #     entry_type=EntryType.DEBIT,
    #     amount=Decimal(state["amount"]),
    #     currency=state["currency"],
    #     status=LedgerStatus.PENDING,
    #     description=f"A2A: {state['reason']}",
    #     reference_type="a2a_intent",
    #     reference_id=state["intent_id"],
    # )
    # session.add(debit_entry)

    placeholder_debit_id = str(_uuid_mod.uuid4())
    log.info(
        "a2a_agent.funds_reserved",
        intent_id=state["intent_id"],
        debit_id=placeholder_debit_id,
    )
    return {"ledger_debit_id": placeholder_debit_id}


async def execute_transfer(state: A2AState) -> dict[str, Any]:
    """Execute SEPA credit transfer via Adyen.

    TODO: Call Adyen EU SEPA SCT API to initiate the transfer.
    For MVP this is a stub that simulates a pending transfer.
    """
    if state.get("error"):
        return {}

    log.info(
        "a2a_agent.execute_transfer",
        intent_id=state["intent_id"],
        amount=state["amount"],
        currency=state["currency"],
    )

    # TODO: Integrate with Adyen EU SEPA SCT API
    # transfer = await adyen_client.create_sepa_transfer(
    #     amount=Decimal(state["amount"]),
    #     currency=state["currency"],
    #     debtor_iban=buyer_iban,
    #     creditor_iban=seller_iban,
    #     reference=state["intent_id"],
    # )

    placeholder_transfer_id = f"SEPA-{_uuid_mod.uuid4().hex[:12].upper()}"
    log.info(
        "a2a_agent.transfer_initiated",
        intent_id=state["intent_id"],
        transfer_id=placeholder_transfer_id,
    )
    return {
        "transfer_id": placeholder_transfer_id,
        "settlement_status": "pending",
    }


async def settle(state: A2AState) -> dict[str, Any]:
    """Credit the seller and update the ledger.

    TODO: Create a ``LedgerEntry`` with ``entry_type=CREDIT`` for the
    seller.  Update both debit and credit entries to ``status=SETTLED``
    once the SEPA transfer is confirmed (T+1).
    """
    if state.get("error"):
        return {}

    log.info(
        "a2a_agent.settle",
        intent_id=state["intent_id"],
        seller=state["seller_agent_id"],
        transfer_id=state.get("transfer_id"),
    )

    # TODO: Create credit ledger entry
    # credit_entry = LedgerEntry(
    #     transaction_id=debit_entry.transaction_id,
    #     account_id=state["seller_agent_id"],
    #     entry_type=EntryType.CREDIT,
    #     amount=Decimal(state["amount"]),
    #     currency=state["currency"],
    #     status=LedgerStatus.PENDING,  # Settled on T+1 via webhook
    #     description=f"A2A: {state['reason']}",
    #     reference_type="a2a_intent",
    #     reference_id=state["intent_id"],
    # )
    # session.add(credit_entry)

    # TODO: Real settlement confirmation comes via Adyen webhook
    # For MVP stub, mark as settled immediately
    placeholder_credit_id = str(_uuid_mod.uuid4())

    log.info(
        "a2a_agent.settled",
        intent_id=state["intent_id"],
        credit_id=placeholder_credit_id,
    )
    return {
        "ledger_credit_id": placeholder_credit_id,
        "settlement_status": "settled",
        "messages": state.get("messages", [])
        + [
            {
                "role": "system",
                "content": f"A2A settlement complete: {state['amount']} {state['currency']} "
                f"from {state['buyer_agent_id']} to {state['seller_agent_id']}",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Error routing
# ---------------------------------------------------------------------------


def _should_continue(state: A2AState) -> Literal["continue", "__end__"]:
    """Abort the graph if an error has been set."""
    if state.get("error"):
        return "__end__"
    return "continue"


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(A2AState)

_builder.add_node("validate_intent", validate_intent)
_builder.add_node("compliance_check", compliance_check)
_builder.add_node("reserve_funds", reserve_funds)
_builder.add_node("execute_transfer", execute_transfer)
_builder.add_node("settle", settle)

_builder.add_edge(START, "validate_intent")
_builder.add_conditional_edges(
    "validate_intent",
    _should_continue,
    {"continue": "compliance_check", "__end__": END},
)
_builder.add_conditional_edges(
    "compliance_check",
    _should_continue,
    {"continue": "reserve_funds", "__end__": END},
)
_builder.add_conditional_edges(
    "reserve_funds",
    _should_continue,
    {"continue": "execute_transfer", "__end__": END},
)
_builder.add_conditional_edges(
    "execute_transfer",
    _should_continue,
    {"continue": "settle", "__end__": END},
)
_builder.add_edge("settle", END)

# Compile with MVP checkpointer
memory = MemorySaver()
a2a_graph = _builder.compile(checkpointer=memory)
"""Compiled A2A settlement graph — invoke with an ``A2AState`` dict."""


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


async def initiate_a2a_payment(
    buyer_agent_id: str,
    seller_agent_id: str,
    amount: str,
    currency: str = "EUR",
    reason: str = "",
) -> A2AState:
    """Initiate an agent-to-agent payment.

    Args:
        buyer_agent_id: UUID (as string) of the paying agent.
        seller_agent_id: UUID (as string) of the receiving agent.
        amount: Payment amount as a decimal string.
        currency: ISO 4217 currency code (default ``"EUR"``).
        reason: Human-readable reason for the payment.

    Returns:
        The final ``A2AState`` after the graph completes.
    """
    intent_id = str(_uuid_mod.uuid4())

    initial_state: A2AState = {
        "intent_id": intent_id,
        "buyer_agent_id": buyer_agent_id,
        "seller_agent_id": seller_agent_id,
        "amount": amount,
        "currency": currency,
        "reason": reason,
        "compliance_passed": None,
        "ledger_debit_id": None,
        "ledger_credit_id": None,
        "transfer_id": None,
        "settlement_status": None,
        "error": None,
        "messages": [],
    }

    config = {"configurable": {"thread_id": f"a2a-{intent_id}"}}

    result = await a2a_graph.ainvoke(initial_state, config=config)
    log.info(
        "a2a_agent.complete",
        intent_id=intent_id,
        settlement_status=result.get("settlement_status"),
        error=result.get("error"),
    )
    return result
