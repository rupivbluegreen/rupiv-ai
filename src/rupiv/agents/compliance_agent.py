"""LangGraph compliance agent — GDPR, DORA, and VAT compliance checks.

Stub implementation for MVP.  Each check node validates a specific
regulatory requirement and records pass/fail.  The ``decide`` node
aggregates results and determines overall compliance.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class ComplianceState(TypedDict):
    """State that flows through the compliance agent graph."""

    transaction_type: str  # "invoice" | "a2a_payment"
    customer_id: str
    amount: str  # Decimal as string
    currency: str
    country_code: str
    checks_passed: list[str]
    checks_failed: list[str]
    is_compliant: bool | None
    messages: list


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def check_gdpr(state: ComplianceState) -> dict[str, Any]:
    """Verify the customer has consent and a data processing agreement.

    Stub: checks that ``customer_id`` is present.  In production this
    would query the consent store and verify DPA status.
    """
    log.info(
        "compliance_agent.check_gdpr",
        customer_id=state["customer_id"],
        transaction_type=state["transaction_type"],
    )

    passed = list(state.get("checks_passed", []))
    failed = list(state.get("checks_failed", []))

    # TODO: Query consent database for active data processing agreement
    # TODO: Verify GDPR Article 6 lawful basis for processing
    # TODO: Check data retention policy compliance

    if not state.get("customer_id"):
        failed.append("gdpr_customer_id_missing")
        log.warning("compliance_agent.gdpr_failed", reason="customer_id missing")
    else:
        passed.append("gdpr_consent")
        passed.append("gdpr_dpa")
        log.info("compliance_agent.gdpr_passed", customer_id=state["customer_id"])

    return {"checks_passed": passed, "checks_failed": failed}


async def check_vat(state: ComplianceState) -> dict[str, Any]:
    """Verify VAT number for B2B and correct VAT rate application.

    Stub: checks that ``country_code`` is a valid 2-letter code and
    ``currency`` is EUR.  In production this would call VIES for VAT
    number validation.
    """
    log.info(
        "compliance_agent.check_vat",
        country_code=state["country_code"],
        currency=state["currency"],
    )

    passed = list(state.get("checks_passed", []))
    failed = list(state.get("checks_failed", []))

    country = state.get("country_code", "")

    # TODO: Call EU VIES API to validate VAT number
    # TODO: Verify correct VAT rate is applied for the country
    # TODO: Check OSS (One Stop Shop) registration for cross-border B2C

    if not country or len(country) != 2:
        failed.append("vat_invalid_country_code")
        log.warning(
            "compliance_agent.vat_failed",
            reason="invalid country code",
            country_code=country,
        )
    else:
        passed.append("vat_country_valid")
        log.info("compliance_agent.vat_passed", country_code=country)

    # Basic currency check for EU transactions
    if country and len(country) == 2 and state.get("currency") not in ("EUR", "USD", "GBP"):
        failed.append("vat_unsupported_currency")
    else:
        passed.append("vat_currency_valid")

    return {"checks_passed": passed, "checks_failed": failed}


async def check_amount_limits(state: ComplianceState) -> dict[str, Any]:
    """Verify the transaction is within allowed limits.

    Stub: enforces a maximum single-transaction amount for A2A payments
    and a minimum invoice amount.  In production these limits would be
    configurable per customer tier.
    """
    log.info(
        "compliance_agent.check_amount_limits",
        amount=state["amount"],
        transaction_type=state["transaction_type"],
    )

    passed = list(state.get("checks_passed", []))
    failed = list(state.get("checks_failed", []))

    try:
        amount = Decimal(state.get("amount", "0"))
    except Exception:
        failed.append("amount_invalid_format")
        return {"checks_passed": passed, "checks_failed": failed}

    # TODO: Load customer-specific limits from DB
    # TODO: Check daily/monthly aggregate limits for DORA compliance
    # TODO: Verify PSD2 Strong Customer Authentication thresholds

    if amount <= Decimal("0"):
        failed.append("amount_non_positive")
        log.warning("compliance_agent.amount_failed", reason="non-positive amount")
    else:
        passed.append("amount_positive")

    # A2A payment limits (SEPA SCT Inst max is 100,000 EUR)
    if state["transaction_type"] == "a2a_payment" and amount > Decimal("100000"):
        failed.append("amount_exceeds_a2a_limit")
        log.warning(
            "compliance_agent.amount_failed",
            reason="exceeds A2A limit",
            amount=str(amount),
        )
    else:
        passed.append("amount_within_limits")

    # Minimum invoice amount
    if state["transaction_type"] == "invoice" and amount < Decimal("0.01"):
        failed.append("amount_below_minimum_invoice")
    else:
        passed.append("amount_above_minimum")

    return {"checks_passed": passed, "checks_failed": failed}


async def decide(state: ComplianceState) -> dict[str, Any]:
    """Aggregate all check results and determine overall compliance.

    Compliant if and only if no checks failed.
    """
    passed = state.get("checks_passed", [])
    failed = state.get("checks_failed", [])

    is_compliant = len(failed) == 0

    log.info(
        "compliance_agent.decide",
        customer_id=state["customer_id"],
        is_compliant=is_compliant,
        checks_passed=passed,
        checks_failed=failed,
    )

    return {
        "is_compliant": is_compliant,
        "messages": state.get("messages", [])
        + [
            {
                "role": "system",
                "content": f"Compliance: {'PASS' if is_compliant else 'FAIL'} "
                f"({len(passed)} passed, {len(failed)} failed)"
                + (f" — failures: {', '.join(failed)}" if failed else ""),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(ComplianceState)

_builder.add_node("check_gdpr", check_gdpr)
_builder.add_node("check_vat", check_vat)
_builder.add_node("check_amount_limits", check_amount_limits)
_builder.add_node("decide", decide)

# Run all checks in sequence (could be parallelised in future)
_builder.add_edge(START, "check_gdpr")
_builder.add_edge("check_gdpr", "check_vat")
_builder.add_edge("check_vat", "check_amount_limits")
_builder.add_edge("check_amount_limits", "decide")
_builder.add_edge("decide", END)

# Compile with MVP checkpointer
memory = MemorySaver()
compliance_graph = _builder.compile(checkpointer=memory)
"""Compiled compliance agent graph — invoke with a ``ComplianceState`` dict."""


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


async def check_compliance(
    transaction_type: str,
    customer_id: str,
    amount: str,
    currency: str = "EUR",
    country_code: str = "NL",
) -> ComplianceState:
    """Run compliance checks for a transaction.

    Args:
        transaction_type: Either ``"invoice"`` or ``"a2a_payment"``.
        customer_id: The UUID (as string) of the customer.
        amount: The transaction amount as a decimal string.
        currency: ISO 4217 currency code (default ``"EUR"``).
        country_code: ISO 3166-1 alpha-2 buyer country (default ``"NL"``).

    Returns:
        The final ``ComplianceState`` after all checks complete.
    """
    import uuid as _uuid

    initial_state: ComplianceState = {
        "transaction_type": transaction_type,
        "customer_id": customer_id,
        "amount": amount,
        "currency": currency,
        "country_code": country_code,
        "checks_passed": [],
        "checks_failed": [],
        "is_compliant": None,
        "messages": [],
    }

    config = {
        "configurable": {
            "thread_id": f"compliance-{customer_id}-{_uuid.uuid4().hex[:8]}"
        }
    }

    result = await compliance_graph.ainvoke(initial_state, config=config)
    log.info(
        "compliance_agent.complete",
        customer_id=customer_id,
        is_compliant=result.get("is_compliant"),
    )
    return result
