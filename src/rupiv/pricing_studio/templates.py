"""Pre-built pricing templates for common AI billing patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PricingTemplate:
    """A ready-to-use pricing template."""

    name: str
    description: str
    category: str
    pricing_rules: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

_TEMPLATES: list[PricingTemplate] = [
    PricingTemplate(
        name="Support AI Outcome Pricing",
        description=(
            "Charge per successfully resolved support ticket. "
            "Only tickets with CSAT >= 3.0 and no escalation are billable."
        ),
        category="outcome",
        pricing_rules=[
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "price_per_outcome": "0.99",
                "outcome_rules": {
                    "billable_when": {
                        "escalated": False,
                        "csat_score_gte": 3.0,
                    },
                    "cap_per_period": 50000,
                    "price_per_outcome": "0.99",
                },
            },
        ],
    ),
    PricingTemplate(
        name="API Platform Usage Pricing",
        description=(
            "Tiered pricing based on token consumption. Lower per-token cost at higher volumes."
        ),
        category="usage",
        pricing_rules=[
            {
                "model": "tiered",
                "metric": "api_tokens",
                "tiers": [
                    {"up_to": 100000, "unit_amount": "0.0010"},
                    {"up_to": 1000000, "unit_amount": "0.0008"},
                    {"up_to": 10000000, "unit_amount": "0.0005"},
                    {"up_to": None, "unit_amount": "0.0003"},
                ],
            },
        ],
    ),
    PricingTemplate(
        name="Hybrid SaaS + AI",
        description=(
            "Fixed monthly base fee plus per-outcome overage charges. "
            "Ideal for SaaS products adding AI-powered features."
        ),
        category="hybrid",
        pricing_rules=[
            {
                "model": "flat",
                "metric": None,
                "flat_amount": "99.00",
            },
            {
                "model": "outcome",
                "metric": "task_completed",
                "price_per_outcome": "0.50",
                "outcome_rules": {
                    "billable_when": {},
                    "cap_per_period": None,
                    "price_per_outcome": "0.50",
                },
            },
        ],
    ),
    PricingTemplate(
        name="Credit Pack",
        description=(
            "Pre-purchased outcome credits. Customers buy credit packs "
            "upfront and consume them as outcomes are delivered."
        ),
        category="credit",
        pricing_rules=[
            {
                "model": "credit",
                "metric": "outcome_credit",
                "outcome_rules": {
                    "credits_per_unit": 1,
                    "credit_rate": "0.05",
                },
            },
        ],
    ),
]


def get_templates() -> list[PricingTemplate]:
    """Return all available pricing templates."""
    log.debug("templates.listed", count=len(_TEMPLATES))
    return list(_TEMPLATES)
