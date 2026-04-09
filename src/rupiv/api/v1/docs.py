"""Developer documentation endpoints — no auth required."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/docs", tags=["docs"])


@router.get(
    "/getting-started",
    summary="Getting-started guide",
    description="Returns a structured JSON guide for integrating with the Rupiv.ai API.",
)
async def getting_started() -> dict:
    """Return a step-by-step getting-started guide as JSON."""
    return {
        "title": "Getting Started with Rupiv.ai",
        "version": "1.0",
        "steps": [
            {
                "step": 1,
                "title": "Create an API key",
                "description": (
                    "POST /v1/api-keys with your account credentials to obtain "
                    "a Bearer token. Include it in the Authorization header of "
                    "every subsequent request."
                ),
                "endpoint": "POST /v1/api-keys",
            },
            {
                "step": 2,
                "title": "Register a customer",
                "description": (
                    "Create a customer record with name, email, country_code, "
                    "and VAT number (for B2B EU reverse-charge). Rupiv.ai "
                    "validates the VAT ID against the VIES registry."
                ),
                "endpoint": "POST /v1/customers",
                "example_body": {
                    "name": "WindmillAI BV",
                    "email": "billing@windmill-ai.nl",
                    "external_id": "wai-001",
                    "country_code": "NL",
                    "currency": "EUR",
                    "is_business": True,
                    "vat_number": "NL862345679B01",
                },
            },
            {
                "step": 3,
                "title": "Create a billing plan",
                "description": (
                    "Define a plan with one or more pricing rules. Supported "
                    "models: flat, usage, outcome, hybrid, tiered, credit."
                ),
                "endpoint": "POST /v1/plans",
                "example_body": {
                    "name": "Support AI Pro",
                    "description": "Per resolved ticket with CSAT gate",
                    "currency": "EUR",
                    "billing_period": "monthly",
                    "pricing_rules": [
                        {
                            "model": "outcome",
                            "metric": "ticket_resolved",
                            "unit_price": "0.9900",
                            "outcome_rules": {
                                "billable_when": {
                                    "csat_score_gte": 3.0,
                                    "escalated": False,
                                },
                                "cap_per_period": 50000,
                            },
                        },
                    ],
                },
            },
            {
                "step": 4,
                "title": "Subscribe the customer",
                "description": (
                    "Attach the customer to a plan by creating a subscription. "
                    "The subscription activates immediately or on a future date."
                ),
                "endpoint": "POST /v1/subscriptions",
            },
            {
                "step": 5,
                "title": "Ingest events",
                "description": (
                    "Send usage or outcome events via POST /v1/events. Each "
                    "event requires an idempotency_key for safe retries. Events "
                    "are queued for async processing and aggregation."
                ),
                "endpoint": "POST /v1/events",
                "example_body": {
                    "type": "outcome",
                    "metric": "ticket_resolved",
                    "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                    "properties": {
                        "resolution_time": 42,
                        "escalated": False,
                        "csat_score": 4.8,
                    },
                    "idempotency_key": "evt-20260409-nl-003-a7c9e2",
                },
            },
            {
                "step": 6,
                "title": "Review invoices",
                "description": (
                    "At the end of each billing period Rupiv.ai generates "
                    "invoices automatically. Line items include EU VAT "
                    "calculated per the customer's country and B2B/B2C status."
                ),
                "endpoint": "GET /v1/invoices",
            },
        ],
        "notes": [
            "All monetary values use EUR by default and are expressed as decimal strings with 4-digit precision.",
            "Timestamps follow ISO 8601 in UTC.",
            "EU VAT reverse-charge is applied automatically for B2B customers with a valid VIES-verified VAT ID.",
            "Rate limits: 1 000 req/min per API key (burst), 100 000 req/day.",
        ],
    }


@router.get(
    "/webhooks",
    summary="Webhook event reference",
    description="Lists all webhook event types Rupiv.ai can emit and their payload formats.",
)
async def webhook_reference() -> dict:
    """Return webhook event types and example payloads."""
    return {
        "title": "Rupiv.ai Webhook Events",
        "version": "1.0",
        "delivery": {
            "method": "POST",
            "content_type": "application/json",
            "signature_header": "X-Rupiv-Signature",
            "signature_algorithm": "HMAC-SHA256",
            "retry_policy": "Exponential back-off, 5 attempts over 24 h. Events are considered failed after the final attempt.",
        },
        "events": [
            {
                "type": "invoice.generated",
                "description": "Fired when a new invoice is created at billing-period end.",
                "payload_example": {
                    "event_type": "invoice.generated",
                    "timestamp": "2026-04-01T02:00:00Z",
                    "data": {
                        "invoice_id": "d4e5f6a7-8901-4bcd-ef23-456789abcdef",
                        "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                        "currency": "EUR",
                        "total": "5989.5000",
                        "status": "open",
                        "due_date": "2026-04-14",
                    },
                },
            },
            {
                "type": "invoice.paid",
                "description": "Fired when payment for an invoice is confirmed by the PSP.",
                "payload_example": {
                    "event_type": "invoice.paid",
                    "timestamp": "2026-04-05T11:32:00Z",
                    "data": {
                        "invoice_id": "d4e5f6a7-8901-4bcd-ef23-456789abcdef",
                        "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                        "amount_paid": "5989.5000",
                        "currency": "EUR",
                        "psp": "mollie",
                        "psp_reference": "tr_WDqYK6vllg",
                    },
                },
            },
            {
                "type": "invoice.payment_failed",
                "description": "Fired when a charge attempt fails. The dunning agent will schedule retries automatically.",
                "payload_example": {
                    "event_type": "invoice.payment_failed",
                    "timestamp": "2026-04-05T11:32:00Z",
                    "data": {
                        "invoice_id": "d4e5f6a7-8901-4bcd-ef23-456789abcdef",
                        "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                        "failure_reason": "insufficient_funds",
                        "retry_scheduled_at": "2026-04-07T11:32:00Z",
                    },
                },
            },
            {
                "type": "subscription.created",
                "description": "Fired when a new subscription is activated.",
                "payload_example": {
                    "event_type": "subscription.created",
                    "timestamp": "2026-03-15T10:00:00Z",
                    "data": {
                        "subscription_id": "a9b8c7d6-e5f4-4321-0987-654321fedcba",
                        "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                        "plan_id": "b1c2d3e4-5f67-4a89-b012-3c4d5e6f7a8b",
                        "status": "active",
                    },
                },
            },
            {
                "type": "subscription.cancelled",
                "description": "Fired when a subscription is cancelled (effective at period end).",
                "payload_example": {
                    "event_type": "subscription.cancelled",
                    "timestamp": "2026-04-08T16:45:00Z",
                    "data": {
                        "subscription_id": "a9b8c7d6-e5f4-4321-0987-654321fedcba",
                        "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                        "effective_end": "2026-04-30T23:59:59Z",
                    },
                },
            },
            {
                "type": "a2a.settled",
                "description": "Fired when an agent-to-agent SEPA payment is settled.",
                "payload_example": {
                    "event_type": "a2a.settled",
                    "timestamp": "2026-04-09T08:00:00Z",
                    "data": {
                        "intent_id": "int-7f3a1b2c",
                        "from_agent_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                        "to_agent_id": "f6e5d4c3-b2a1-4098-7654-3210fedcba98",
                        "amount": "24.5000",
                        "currency": "EUR",
                        "psp_reference": "adyen-sepa-9x8y7z",
                    },
                },
            },
            {
                "type": "a2a.failed",
                "description": "Fired when an agent-to-agent payment fails compliance or settlement.",
                "payload_example": {
                    "event_type": "a2a.failed",
                    "timestamp": "2026-04-09T08:01:00Z",
                    "data": {
                        "intent_id": "int-9a8b7c6d",
                        "from_agent_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                        "to_agent_id": "f6e5d4c3-b2a1-4098-7654-3210fedcba98",
                        "error": "compliance_rejected: amount exceeds daily threshold",
                    },
                },
            },
            {
                "type": "credit.depleted",
                "description": "Fired when a customer's credit balance reaches zero.",
                "payload_example": {
                    "event_type": "credit.depleted",
                    "timestamp": "2026-04-08T22:15:00Z",
                    "data": {
                        "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                        "credit_balance": "0.0000",
                        "currency": "EUR",
                    },
                },
            },
            {
                "type": "quote.accepted",
                "description": "Fired when a prospect accepts a pricing quote.",
                "payload_example": {
                    "event_type": "quote.accepted",
                    "timestamp": "2026-04-02T14:20:00Z",
                    "data": {
                        "quote_id": "q-12345678",
                        "customer_id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                        "plan_id": "b1c2d3e4-5f67-4a89-b012-3c4d5e6f7a8b",
                        "total_contract_value": "11880.0000",
                        "currency": "EUR",
                    },
                },
            },
        ],
    }
