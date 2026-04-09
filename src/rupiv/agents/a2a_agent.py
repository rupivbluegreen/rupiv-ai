"""LangGraph agent-to-agent (A2A) SEPA settlement agent.

Orchestrates autonomous payments between AI agents via SEPA fiat rails
(Adyen EU), with compliance checks and double-entry ledger bookkeeping.

Flow: validate_intent -> compliance_check -> reserve_funds -> execute_transfer -> settle
Each node can set ``error`` to abort the graph early via conditional edges.
"""

from __future__ import annotations

import uuid as _uuid_mod
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from rupiv.billing import ledger
from rupiv.billing.adyen_client import AdyenClient, AdyenTransfer
from rupiv.config import get_settings
from rupiv.policy.engine import PolicyEngine
from rupiv.policy.rules import PolicyRuleData

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Currencies supported for A2A SEPA transfers (EUR-only for MVP)
SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"EUR"})

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
    seller_iban: str | None
    seller_bic: str | None
    compliance_passed: bool | None
    ledger_transaction_id: str | None
    ledger_debit_id: str | None
    ledger_credit_id: str | None
    transfer_id: str | None  # SEPA transfer / PSP reference
    psp_reference: str | None
    settlement_status: str | None  # "pending" | "settled" | "failed"
    error: str | None
    messages: list


# ---------------------------------------------------------------------------
# Module-level singletons (lazy-initialised)
# ---------------------------------------------------------------------------

_adyen_client: AdyenClient | None = None
_policy_engine: PolicyEngine = PolicyEngine()

# In-memory store for agent accounts (replace with DB in production)
# Maps agent_id -> {"iban": str, "bic": str | None, "active": bool}
_agent_accounts: dict[str, dict[str, Any]] = {}

# In-memory store for policy rules (replace with DB in production)
_policy_rules: list[PolicyRuleData] = []


def get_adyen_client() -> AdyenClient:
    """Return the module-level AdyenClient, creating it on first call."""
    global _adyen_client
    if _adyen_client is None:
        settings = get_settings()
        api_key = settings.ADYEN_API_KEY or ""
        merchant = settings.ADYEN_MERCHANT_ACCOUNT or ""
        _adyen_client = AdyenClient(api_key=api_key, merchant_account=merchant)
    return _adyen_client


def register_agent_account(
    agent_id: str,
    iban: str,
    bic: str | None = None,
    active: bool = True,
) -> None:
    """Register an agent account for A2A payments (test/seed helper)."""
    _agent_accounts[agent_id] = {"iban": iban, "bic": bic, "active": active}


def set_policy_rules(rules: list[PolicyRuleData]) -> None:
    """Set the active policy rules for A2A compliance checks."""
    global _policy_rules
    _policy_rules = list(rules)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def validate_intent(state: A2AState) -> dict[str, Any]:
    """Check that both agents exist, amount is valid, and currency supported."""
    log.info(
        "a2a_agent.validate_intent",
        intent_id=state["intent_id"],
        buyer=state["buyer_agent_id"],
        seller=state["seller_agent_id"],
        amount=state["amount"],
    )

    # Parse and validate amount
    try:
        amount = Decimal(state.get("amount", "0"))
    except (InvalidOperation, TypeError, ValueError):
        return {"error": "Invalid amount format"}

    if amount <= Decimal("0"):
        return {"error": "Amount must be positive"}

    # Validate agent IDs
    if not state.get("buyer_agent_id"):
        return {"error": "Buyer agent ID is required"}

    if not state.get("seller_agent_id"):
        return {"error": "Seller agent ID is required"}

    if state["buyer_agent_id"] == state["seller_agent_id"]:
        return {"error": "Buyer and seller cannot be the same agent"}

    # Verify both agents exist in registry
    buyer_account = _agent_accounts.get(state["buyer_agent_id"])
    if buyer_account is None:
        return {"error": f"Buyer agent {state['buyer_agent_id']} not found"}

    if not buyer_account.get("active", False):
        return {"error": f"Buyer agent {state['buyer_agent_id']} is not active"}

    seller_account = _agent_accounts.get(state["seller_agent_id"])
    if seller_account is None:
        return {"error": f"Seller agent {state['seller_agent_id']} not found"}

    if not seller_account.get("active", False):
        return {"error": f"Seller agent {state['seller_agent_id']} is not active"}

    # Validate currency
    currency = state.get("currency", "EUR").upper()
    if currency not in SUPPORTED_CURRENCIES:
        return {
            "error": f"Currency {currency} not supported for A2A. Supported: {', '.join(sorted(SUPPORTED_CURRENCIES))}",
        }

    log.info("a2a_agent.intent_valid", intent_id=state["intent_id"])
    return {
        "seller_iban": seller_account["iban"],
        "seller_bic": seller_account.get("bic"),
        "messages": state.get("messages", [])
        + [{"role": "system", "content": "A2A intent validated"}],
    }


async def compliance_check(state: A2AState) -> dict[str, Any]:
    """Run policy rules for a2a.payment trigger against this transaction."""
    if state.get("error"):
        return {}

    log.info(
        "a2a_agent.compliance_check",
        intent_id=state["intent_id"],
        amount=state["amount"],
        currency=state["currency"],
    )

    # Filter rules for a2a.payment trigger
    a2a_rules = [r for r in _policy_rules if r.trigger == "a2a.payment"]

    if a2a_rules:
        context = {
            "payment": {
                "amount": Decimal(state["amount"]),
                "currency": state["currency"],
                "buyer_agent_id": state["buyer_agent_id"],
                "seller_agent_id": state["seller_agent_id"],
                "reason": state.get("reason", ""),
            },
        }

        result = _policy_engine.evaluate(context, a2a_rules)

        if result.action == "reject":
            log.warning(
                "a2a_agent.compliance_rejected",
                intent_id=state["intent_id"],
                rule=result.rule_name,
                reason=result.reason,
            )
            return {
                "error": f"Compliance check failed: {result.reason}",
                "compliance_passed": False,
            }

    log.info("a2a_agent.compliance_passed", intent_id=state["intent_id"])
    return {"compliance_passed": True}


async def reserve_funds(state: A2AState) -> dict[str, Any]:
    """Create a pending debit+credit pair and verify buyer has sufficient balance."""
    if state.get("error"):
        return {}

    log.info(
        "a2a_agent.reserve_funds",
        intent_id=state["intent_id"],
        buyer=state["buyer_agent_id"],
        amount=state["amount"],
    )

    amount = Decimal(state["amount"])

    # Check buyer has sufficient available balance
    available = await ledger.get_available_balance(state["buyer_agent_id"])
    if available < amount:
        log.warning(
            "a2a_agent.insufficient_balance",
            intent_id=state["intent_id"],
            available=str(available),
            required=str(amount),
        )
        return {
            "error": f"Insufficient balance: available={available}, required={amount}",
        }

    # Create the pending double-entry transfer
    transaction_id = await ledger.create_transfer(
        from_account=state["buyer_agent_id"],
        to_account=state["seller_agent_id"],
        amount=amount,
        currency=state["currency"],
        description=f"A2A: {state.get('reason', 'agent payment')}",
    )

    # Retrieve entry IDs for state tracking
    entries = await ledger.get_entries_by_transaction(transaction_id)
    debit_id: str | None = None
    credit_id: str | None = None
    for entry in entries:
        if entry.entry_type == ledger.EntryType.DEBIT:
            debit_id = entry.entry_id
        elif entry.entry_type == ledger.EntryType.CREDIT:
            credit_id = entry.entry_id

    log.info(
        "a2a_agent.funds_reserved",
        intent_id=state["intent_id"],
        transaction_id=transaction_id,
        debit_id=debit_id,
    )
    return {
        "ledger_transaction_id": transaction_id,
        "ledger_debit_id": debit_id,
        "ledger_credit_id": credit_id,
    }


async def execute_transfer(state: A2AState) -> dict[str, Any]:
    """Execute SEPA credit transfer via Adyen."""
    if state.get("error"):
        return {}

    log.info(
        "a2a_agent.execute_transfer",
        intent_id=state["intent_id"],
        amount=state["amount"],
        currency=state["currency"],
    )

    seller_iban = state.get("seller_iban", "")
    seller_bic = state.get("seller_bic")

    if not seller_iban:
        return {"error": "Seller IBAN not available"}

    client = get_adyen_client()

    try:
        transfer: AdyenTransfer = await client.create_sepa_transfer(
            amount=Decimal(state["amount"]),
            currency=state["currency"],
            iban=seller_iban,
            bic=seller_bic,
            reference=state["intent_id"],
            description=f"A2A: {state.get('reason', 'agent payment')}",
        )
    except Exception as exc:
        log.error(
            "a2a_agent.transfer_error",
            intent_id=state["intent_id"],
            error=str(exc),
        )
        return {
            "error": f"SEPA transfer failed: {exc}",
            "settlement_status": "failed",
        }

    log.info(
        "a2a_agent.transfer_initiated",
        intent_id=state["intent_id"],
        psp_reference=transfer.psp_reference,
        status=transfer.status,
    )
    return {
        "transfer_id": transfer.psp_reference,
        "psp_reference": transfer.psp_reference,
        "settlement_status": "pending" if transfer.status != "Refused" else "failed",
        "error": f"Transfer refused by Adyen: {transfer.psp_reference}"
        if transfer.status == "Refused"
        else None,
    }


async def settle(state: A2AState) -> dict[str, Any]:
    """Finalize the ledger based on Adyen transfer result.

    If Adyen returned ``"Authorised"`` or ``"Pending"``, settle the
    double-entry transaction.  If ``"Refused"``, reverse the reservation
    by marking entries as failed.

    SEPA settlement is T+1 in reality; for the graph flow we settle on
    Authorised and leave webhook-based reconciliation for production.
    """
    if state.get("error"):
        # If there was a transfer error, reverse the ledger reservation
        tx_id = state.get("ledger_transaction_id")
        if tx_id:
            try:
                await ledger.fail_transaction(tx_id)
                log.info(
                    "a2a_agent.reservation_reversed",
                    intent_id=state["intent_id"],
                    transaction_id=tx_id,
                )
            except ValueError:
                pass  # Transaction not found — nothing to reverse
        return {"settlement_status": "failed"}

    log.info(
        "a2a_agent.settle",
        intent_id=state["intent_id"],
        seller=state["seller_agent_id"],
        transfer_id=state.get("transfer_id"),
        psp_reference=state.get("psp_reference"),
    )

    tx_id = state.get("ledger_transaction_id")
    if not tx_id:
        return {"error": "No ledger transaction to settle", "settlement_status": "failed"}

    # Settle the double-entry transaction (debit + credit both -> SETTLED)
    try:
        await ledger.settle_transaction(tx_id)
    except ValueError as exc:
        log.error(
            "a2a_agent.settle_error",
            intent_id=state["intent_id"],
            error=str(exc),
        )
        return {"error": f"Settlement failed: {exc}", "settlement_status": "failed"}

    log.info(
        "a2a_agent.settled",
        intent_id=state["intent_id"],
        transaction_id=tx_id,
    )
    return {
        "settlement_status": "settled",
        "messages": state.get("messages", [])
        + [
            {
                "role": "system",
                "content": f"A2A settlement complete: {state['amount']} {state['currency']} "
                f"from {state['buyer_agent_id']} to {state['seller_agent_id']}",
            },
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
"""Compiled A2A settlement graph -- invoke with an ``A2AState`` dict."""


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
        "seller_iban": None,
        "seller_bic": None,
        "compliance_passed": None,
        "ledger_transaction_id": None,
        "ledger_debit_id": None,
        "ledger_credit_id": None,
        "transfer_id": None,
        "psp_reference": None,
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
