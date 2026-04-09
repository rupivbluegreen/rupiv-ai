"""Seed the database with realistic demo data for development."""

from __future__ import annotations

import argparse
import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.db import Base, _get_engine, _get_session_factory
from rupiv.models.customer import Customer
from rupiv.models.event import Event, EventType, OutcomeStatus
from rupiv.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus, TaxType
from rupiv.models.plan import BillingInterval, Plan, PricingModel, PricingRule
from rupiv.models.subscription import Subscription, SubscriptionStatus
from rupiv.models.entity import EntityType, LegalEntity
from rupiv.models.policy_rule import PolicyRule
from rupiv.models.quote import Quote, QuoteLineItem, QuoteStatus
from rupiv.models.contract import Contract, ContractRenewalType, ContractStatus

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_NOW = datetime.now(tz=timezone.utc)


def _months_ago(n: int) -> datetime:
    """Return a timezone-aware datetime *n* months before now (approx)."""
    return _NOW - timedelta(days=30 * n)


def _period_start(dt: datetime) -> datetime:
    """First day of the month for *dt*."""
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _period_end(dt: datetime) -> datetime:
    """Last moment of the month for *dt*."""
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)
    return next_month - timedelta(microseconds=1)


def _random_ts(start: datetime, end: datetime) -> datetime:
    """Return a random timezone-aware timestamp between *start* and *end*."""
    delta = (end - start).total_seconds()
    offset = random.random() * delta
    return start + timedelta(seconds=offset)


def _inv_number(period: datetime, seq: int) -> str:
    """Generate invoice number in INV-YYYYMM-XXXXX format."""
    return f"INV-{period.strftime('%Y%m')}-{seq:05d}"


# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------

CUSTOMERS: list[dict[str, Any]] = [
    {
        "external_id": "cust_resolvai",
        "name": "ResolvAI",
        "email": "billing@resolvai.nl",
        "billing_email": "finance@resolvai.nl",
        "country_code": "NL",
        "vat_number": "NL123456789B01",
        "is_business": True,
        "currency": "EUR",
        "metadata_": {"industry": "support_ai", "tier": "growth"},
    },
    {
        "external_id": "cust_fraudshield",
        "name": "FraudShield",
        "email": "billing@fraudshield.de",
        "billing_email": "accounts@fraudshield.de",
        "country_code": "DE",
        "vat_number": "DE123456789",
        "is_business": True,
        "currency": "EUR",
        "metadata_": {"industry": "fraud_detection_ai", "tier": "scale"},
    },
    {
        "external_id": "cust_legalmind",
        "name": "LegalMind",
        "email": "billing@legalmind.fr",
        "billing_email": None,
        "country_code": "FR",
        "vat_number": None,
        "is_business": True,
        "currency": "EUR",
        "metadata_": {"industry": "legal_ai", "tier": "growth"},
    },
    {
        "external_id": "cust_devopsbot",
        "name": "DevOpsBot",
        "email": "billing@devopsbot.nl",
        "billing_email": "finance@devopsbot.nl",
        "country_code": "NL",
        "vat_number": None,
        "is_business": True,
        "currency": "EUR",
        "metadata_": {"industry": "devops_ai", "tier": "enterprise"},
    },
    {
        "external_id": "cust_marketgenius",
        "name": "MarketGenius",
        "email": "hello@marketgenius.be",
        "billing_email": None,
        "country_code": "BE",
        "vat_number": None,
        "is_business": False,
        "currency": "EUR",
        "metadata_": {"industry": "marketing_ai", "tier": "starter"},
    },
]


def _build_plans() -> list[dict[str, Any]]:
    """Return plan definitions with nested pricing rules."""
    starter_id = uuid.uuid4()
    growth_id = uuid.uuid4()
    scale_id = uuid.uuid4()
    enterprise_id = uuid.uuid4()

    return [
        {
            "id": starter_id,
            "name": "Starter",
            "description": "Fixed monthly plan for small teams getting started.",
            "is_active": True,
            "currency": "EUR",
            "rules": [
                {
                    "plan_id": starter_id,
                    "pricing_model": PricingModel.FLAT,
                    "metric": None,
                    "unit_amount": None,
                    "flat_amount": Decimal("49.0000"),
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": None,
                },
            ],
        },
        {
            "id": growth_id,
            "name": "Growth",
            "description": (
                "Base fee plus usage and outcome pricing. "
                "Ideal for scaling AI products."
            ),
            "is_active": True,
            "currency": "EUR",
            "rules": [
                {
                    "plan_id": growth_id,
                    "pricing_model": PricingModel.FLAT,
                    "metric": None,
                    "unit_amount": None,
                    "flat_amount": Decimal("149.0000"),
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": None,
                },
                {
                    "plan_id": growth_id,
                    "pricing_model": PricingModel.USAGE,
                    "metric": "api_call",
                    "unit_amount": Decimal("0.1000"),
                    "flat_amount": None,
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": {"per_unit": 1000},
                },
                {
                    "plan_id": growth_id,
                    "pricing_model": PricingModel.OUTCOME,
                    "metric": "ticket_resolved",
                    "unit_amount": Decimal("0.9900"),
                    "flat_amount": None,
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": {
                        "billable_when": {
                            "escalated": False,
                            "csat_score_gte": 3.0,
                        },
                    },
                },
            ],
        },
        {
            "id": scale_id,
            "name": "Scale",
            "description": (
                "High-volume plan with usage, outcome, and tiered pricing."
            ),
            "is_active": True,
            "currency": "EUR",
            "rules": [
                {
                    "plan_id": scale_id,
                    "pricing_model": PricingModel.FLAT,
                    "metric": None,
                    "unit_amount": None,
                    "flat_amount": Decimal("499.0000"),
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": None,
                },
                {
                    "plan_id": scale_id,
                    "pricing_model": PricingModel.USAGE,
                    "metric": "api_call",
                    "unit_amount": Decimal("0.0600"),
                    "flat_amount": None,
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": {"per_unit": 1000},
                },
                {
                    "plan_id": scale_id,
                    "pricing_model": PricingModel.OUTCOME,
                    "metric": "fraud_prevented",
                    "unit_amount": Decimal("1.5000"),
                    "flat_amount": None,
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": {"cap_per_period": 50000},
                },
                {
                    "plan_id": scale_id,
                    "pricing_model": PricingModel.TIERED,
                    "metric": "api_call",
                    "unit_amount": None,
                    "flat_amount": None,
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": [
                        {"up_to": 1000, "unit_amount": "0.0100"},
                        {"up_to": 10000, "unit_amount": "0.0080"},
                        {"up_to": None, "unit_amount": "0.0050"},
                    ],
                    "outcome_rules": None,
                },
            ],
        },
        {
            "id": enterprise_id,
            "name": "Enterprise",
            "description": (
                "Premium plan with dedicated support and outcome billing."
            ),
            "is_active": True,
            "currency": "EUR",
            "rules": [
                {
                    "plan_id": enterprise_id,
                    "pricing_model": PricingModel.FLAT,
                    "metric": None,
                    "unit_amount": None,
                    "flat_amount": Decimal("2000.0000"),
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": None,
                },
                {
                    "plan_id": enterprise_id,
                    "pricing_model": PricingModel.OUTCOME,
                    "metric": "task_completed",
                    "unit_amount": Decimal("2.5000"),
                    "flat_amount": None,
                    "currency": "EUR",
                    "billing_interval": BillingInterval.MONTHLY,
                    "tiers": None,
                    "outcome_rules": None,
                },
            ],
        },
    ]


# Map customer external_id -> plan name and months_ago for subscription start
SUBSCRIPTION_MAP: dict[str, tuple[str, int]] = {
    "cust_resolvai": ("Growth", 3),
    "cust_fraudshield": ("Scale", 2),
    "cust_legalmind": ("Growth", 1),
    "cust_devopsbot": ("Enterprise", 4),
    "cust_marketgenius": ("Starter", 2),
}

# Metrics per plan for event generation
PLAN_METRICS: dict[str, list[dict[str, Any]]] = {
    "Growth": [
        {
            "metric": "api_call",
            "event_type": EventType.USAGE,
            "weight": 5,
        },
        {
            "metric": "ticket_resolved",
            "event_type": EventType.OUTCOME,
            "weight": 3,
        },
    ],
    "Scale": [
        {
            "metric": "api_call",
            "event_type": EventType.USAGE,
            "weight": 6,
        },
        {
            "metric": "fraud_prevented",
            "event_type": EventType.OUTCOME,
            "weight": 4,
        },
    ],
    "Enterprise": [
        {
            "metric": "api_call",
            "event_type": EventType.USAGE,
            "weight": 3,
        },
        {
            "metric": "task_completed",
            "event_type": EventType.OUTCOME,
            "weight": 5,
        },
        {
            "metric": "document_reviewed",
            "event_type": EventType.OUTCOME,
            "weight": 2,
        },
    ],
    "Starter": [
        {
            "metric": "api_call",
            "event_type": EventType.USAGE,
            "weight": 2,
        },
    ],
}


def _outcome_properties(metric: str) -> dict[str, Any]:
    """Generate realistic properties for an outcome event."""
    if metric == "ticket_resolved":
        escalated = random.random() < 0.15
        return {
            "resolution_time": random.randint(15, 600),
            "escalated": escalated,
            "csat_score": round(random.uniform(1.0, 5.0), 1),
            "channel": random.choice(["chat", "email", "phone"]),
        }
    if metric == "fraud_prevented":
        return {
            "amount_saved": round(random.uniform(50.0, 5000.0), 2),
            "fraud_type": random.choice(
                ["card_not_present", "account_takeover", "identity_theft"]
            ),
            "confidence": round(random.uniform(0.7, 1.0), 3),
        }
    if metric == "task_completed":
        return {
            "task_type": random.choice(
                ["deploy", "rollback", "scale_up", "alert_triage", "incident_resolve"]
            ),
            "duration_seconds": random.randint(5, 1200),
            "automated": random.random() > 0.1,
        }
    if metric == "document_reviewed":
        return {
            "document_type": random.choice(
                ["contract", "nda", "terms_of_service", "privacy_policy"]
            ),
            "pages": random.randint(1, 120),
            "issues_found": random.randint(0, 15),
        }
    # api_call — usage events have minimal properties
    return {
        "endpoint": random.choice(
            ["/v1/analyze", "/v1/predict", "/v1/classify", "/v1/embed"]
        ),
        "response_ms": random.randint(10, 800),
    }


def _outcome_status_for(metric: str) -> OutcomeStatus | None:
    """Assign a realistic outcome status."""
    if metric == "api_call":
        return None  # usage events have no outcome status
    roll = random.random()
    if roll < 0.70:
        return OutcomeStatus.VALIDATED
    if roll < 0.90:
        return OutcomeStatus.PENDING
    return OutcomeStatus.REJECTED


# ---------------------------------------------------------------------------
# EU VAT helpers
# ---------------------------------------------------------------------------
_EU_VAT_RATES: dict[str, Decimal] = {
    "NL": Decimal("0.2100"),
    "DE": Decimal("0.1900"),
    "FR": Decimal("0.2000"),
    "BE": Decimal("0.2100"),
}


def _tax_for_customer(customer: Customer) -> tuple[Decimal, TaxType | None]:
    """Return (tax_rate, tax_type) applying EU reverse-charge rules."""
    if customer.is_business and customer.country_code != "NL":
        # B2B intra-EU: reverse charge, 0 % on invoice
        return Decimal("0.0000"), TaxType.REVERSE_CHARGE
    if customer.is_business and customer.country_code == "NL":
        # Domestic B2B: standard Dutch VAT
        return _EU_VAT_RATES.get("NL", Decimal("0.2100")), TaxType.STANDARD
    # B2C: standard rate of customer country
    rate = _EU_VAT_RATES.get(customer.country_code, Decimal("0.2100"))
    return rate, TaxType.STANDARD


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

async def _ensure_tables(session: AsyncSession) -> None:
    """Check whether the tables exist; advise running migrations if not."""
    try:
        await session.execute(text("SELECT 1 FROM customers LIMIT 1"))
    except Exception:
        log.error(
            "tables_not_found",
            hint="Run 'make migrate' (alembic upgrade head) before seeding.",
        )
        raise SystemExit(1)


async def _is_empty(session: AsyncSession) -> bool:
    """Return True if the customers table has zero rows."""
    result = await session.execute(select(Customer).limit(1))
    return result.scalars().first() is None


async def _wipe(session: AsyncSession) -> None:
    """Delete all seeded data in reverse dependency order."""
    log.info("wiping_existing_data")
    await session.execute(text("DELETE FROM contracts"))
    await session.execute(text("DELETE FROM quote_line_items"))
    await session.execute(text("DELETE FROM quotes"))
    await session.execute(text("DELETE FROM approval_records"))
    await session.execute(text("DELETE FROM policy_rules"))
    await session.execute(text("DELETE FROM legal_entities"))
    await session.execute(text("DELETE FROM invoice_line_items"))
    await session.execute(text("DELETE FROM invoices"))
    await session.execute(text("DELETE FROM events"))
    await session.execute(text("DELETE FROM subscriptions"))
    await session.execute(text("DELETE FROM pricing_rules"))
    await session.execute(text("DELETE FROM plans"))
    await session.execute(text("DELETE FROM customers"))
    await session.commit()
    log.info("wipe_complete")


async def _seed_customers(session: AsyncSession) -> list[Customer]:
    """Insert demo customers."""
    customers: list[Customer] = []
    for data in CUSTOMERS:
        cust = Customer(**data)
        session.add(cust)
        customers.append(cust)
    await session.flush()
    log.info("customers_created", count=len(customers))
    return customers


async def _seed_plans(session: AsyncSession) -> list[Plan]:
    """Insert demo plans with pricing rules."""
    plans_data = _build_plans()
    plans: list[Plan] = []
    for pdata in plans_data:
        rules_data = pdata.pop("rules")
        plan = Plan(**pdata)
        session.add(plan)
        await session.flush()
        for rdata in rules_data:
            rdata["plan_id"] = plan.id
            rule = PricingRule(**rdata)
            session.add(rule)
        plans.append(plan)
    await session.flush()
    log.info("plans_created", count=len(plans))
    return plans


async def _seed_subscriptions(
    session: AsyncSession,
    customers: list[Customer],
    plans: list[Plan],
) -> list[Subscription]:
    """Create one subscription per customer."""
    plan_by_name: dict[str, Plan] = {p.name: p for p in plans}
    cust_by_ext: dict[str, Customer] = {c.external_id: c for c in customers}
    subs: list[Subscription] = []

    for ext_id, (plan_name, months) in SUBSCRIPTION_MAP.items():
        cust = cust_by_ext[ext_id]
        plan = plan_by_name[plan_name]
        start = _months_ago(months)
        sub = Subscription(
            customer_id=cust.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=_period_start(_NOW),
            current_period_end=_period_end(_NOW),
        )
        sub._seed_start = start  # type: ignore[attr-defined]  # stash for event gen
        sub._plan_name = plan_name  # type: ignore[attr-defined]
        session.add(sub)
        subs.append(sub)

    await session.flush()
    log.info("subscriptions_created", count=len(subs))
    return subs


async def _seed_events(
    session: AsyncSession,
    customers: list[Customer],
    subs: list[Subscription],
) -> list[Event]:
    """Generate ~200 events spread across the last 3 months."""
    cust_by_id: dict[uuid.UUID, Customer] = {c.id: c for c in customers}
    events: list[Event] = []
    target_count = 200

    # Build weighted pool of (subscription, metric_info) pairs
    pool: list[tuple[Subscription, dict[str, Any]]] = []
    for sub in subs:
        plan_name: str = sub._plan_name  # type: ignore[attr-defined]
        metrics = PLAN_METRICS.get(plan_name, [])
        for m in metrics:
            for _ in range(m["weight"]):
                pool.append((sub, m))

    if not pool:
        log.warning("no_event_pool")
        return events

    three_months_ago = _months_ago(3)

    for i in range(target_count):
        sub, metric_info = random.choice(pool)
        metric: str = metric_info["metric"]
        event_type: EventType = metric_info["event_type"]
        start_bound: datetime = sub._seed_start  # type: ignore[attr-defined]
        ts = _random_ts(max(start_bound, three_months_ago), _NOW)

        props = _outcome_properties(metric)
        outcome_st = _outcome_status_for(metric)

        evt = Event(
            customer_id=sub.customer_id,
            subscription_id=sub.id,
            event_type=event_type,
            metric=metric,
            properties=props,
            idempotency_key=f"seed-{uuid.uuid4().hex[:16]}-{i}",
            outcome_status=outcome_st,
            timestamp=ts,
        )
        session.add(evt)
        events.append(evt)

    await session.flush()
    log.info("events_created", count=len(events))
    return events


async def _seed_invoices(
    session: AsyncSession,
    customers: list[Customer],
    plans: list[Plan],
    subs: list[Subscription],
) -> list[Invoice]:
    """Generate ~10 invoices across subscriptions for past months."""
    plan_by_name: dict[str, Plan] = {p.name: p for p in plans}
    cust_by_id: dict[uuid.UUID, Customer] = {c.id: c for c in customers}
    invoices: list[Invoice] = []
    inv_seq = 1

    # For each subscription, generate invoices for completed months
    for sub in subs:
        plan_name: str = sub._plan_name  # type: ignore[attr-defined]
        start: datetime = sub._seed_start  # type: ignore[attr-defined]
        plan = plan_by_name[plan_name]
        customer = cust_by_id[sub.customer_id]
        tax_rate, tax_type = _tax_for_customer(customer)

        # Walk months from subscription start to now
        cursor = _period_start(start)
        current_month_start = _period_start(_NOW)

        while cursor <= current_month_start:
            p_start = _period_start(cursor)
            p_end = _period_end(cursor)
            is_current = cursor.month == _NOW.month and cursor.year == _NOW.year

            # Determine status
            if is_current:
                status = InvoiceStatus.OPEN
            elif cursor == _period_start(start):
                # first month might be draft for variety
                status = InvoiceStatus.DRAFT if random.random() < 0.3 else InvoiceStatus.PAID
            else:
                status = InvoiceStatus.PAID

            # Build line items based on plan rules
            line_items_data: list[dict[str, Any]] = []
            subtotal = Decimal("0.0000")

            for rule in plan.pricing_rules:
                if rule.pricing_model == PricingModel.FLAT and rule.flat_amount:
                    amt = rule.flat_amount
                    line_items_data.append({
                        "description": f"{plan.name} plan — monthly base fee",
                        "quantity": Decimal("1.0000"),
                        "unit_amount": amt,
                        "amount": amt,
                        "metric": None,
                        "pricing_model": "flat",
                    })
                    subtotal += amt

                elif rule.pricing_model == PricingModel.USAGE and rule.unit_amount:
                    # Simulate usage quantity
                    qty = Decimal(str(random.randint(5000, 50000)))
                    per_unit = rule.unit_amount
                    per_k = rule.outcome_rules.get("per_unit", 1) if rule.outcome_rules else 1
                    units = qty / Decimal(str(per_k))
                    amt = (units * per_unit).quantize(Decimal("0.0001"))
                    line_items_data.append({
                        "description": f"Usage: {rule.metric} ({int(qty)} events)",
                        "quantity": units,
                        "unit_amount": per_unit,
                        "amount": amt,
                        "metric": rule.metric,
                        "pricing_model": "usage",
                    })
                    subtotal += amt

                elif rule.pricing_model == PricingModel.OUTCOME and rule.unit_amount:
                    qty = Decimal(str(random.randint(20, 300)))
                    amt = (qty * rule.unit_amount).quantize(Decimal("0.0001"))
                    line_items_data.append({
                        "description": (
                            f"Outcome: {rule.metric} ({int(qty)} billable)"
                        ),
                        "quantity": qty,
                        "unit_amount": rule.unit_amount,
                        "amount": amt,
                        "metric": rule.metric,
                        "pricing_model": "outcome",
                    })
                    subtotal += amt

                elif rule.pricing_model == PricingModel.TIERED and rule.tiers:
                    total_qty = random.randint(2000, 15000)
                    tier_amt = Decimal("0.0000")
                    remaining = total_qty
                    prev_limit = 0
                    for tier in rule.tiers:
                        up_to = tier.get("up_to") or remaining + prev_limit
                        bracket_size = min(remaining, up_to - prev_limit)
                        if bracket_size <= 0:
                            break
                        tier_price = Decimal(str(tier["unit_amount"]))
                        tier_amt += (Decimal(str(bracket_size)) * tier_price).quantize(
                            Decimal("0.0001")
                        )
                        remaining -= bracket_size
                        prev_limit = up_to
                    line_items_data.append({
                        "description": (
                            f"Tiered: {rule.metric} ({total_qty} events)"
                        ),
                        "quantity": Decimal(str(total_qty)),
                        "unit_amount": Decimal("0.0000"),
                        "amount": tier_amt,
                        "metric": rule.metric,
                        "pricing_model": "tiered",
                    })
                    subtotal += tier_amt

            tax_amount = (subtotal * tax_rate).quantize(Decimal("0.0001"))
            total = subtotal + tax_amount
            due = (p_end + timedelta(days=14)).date()
            paid_at_val: datetime | None = None
            if status == InvoiceStatus.PAID:
                paid_at_val = p_end + timedelta(days=random.randint(1, 10))

            inv = Invoice(
                customer_id=sub.customer_id,
                subscription_id=sub.id,
                invoice_number=_inv_number(p_start, inv_seq),
                status=status,
                subtotal=subtotal,
                tax_amount=tax_amount,
                total=total,
                currency="EUR",
                tax_rate=tax_rate,
                tax_type=tax_type,
                period_start=p_start,
                period_end=p_end,
                due_date=due,
                paid_at=paid_at_val,
                mollie_payment_id=f"tr_{uuid.uuid4().hex[:12]}" if status == InvoiceStatus.PAID else None,
            )
            session.add(inv)
            await session.flush()

            for li_data in line_items_data:
                li = InvoiceLineItem(invoice_id=inv.id, **li_data)
                session.add(li)

            invoices.append(inv)
            inv_seq += 1

            # Advance to next month
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)

    await session.flush()
    log.info("invoices_created", count=len(invoices))
    return invoices


# ---------------------------------------------------------------------------
# New-module seed helpers (entities, policy rules, quotes, contracts)
# ---------------------------------------------------------------------------

async def _seed_entities(session: AsyncSession) -> list[LegalEntity]:
    """Insert a parent BV + two child entities (GmbH, SAS)."""
    parent = LegalEntity(
        name="Rupiv BV",
        entity_type=EntityType.BV,
        country_code="NL",
        vat_number="NL861234567B01",
        registration_number="KVK-12345678",
        default_currency="EUR",
    )
    session.add(parent)
    await session.flush()

    gmbh = LegalEntity(
        name="Rupiv GmbH",
        entity_type=EntityType.GMBH,
        country_code="DE",
        vat_number="DE312345678",
        registration_number="HRB-98765",
        default_currency="EUR",
        parent_id=parent.id,
    )
    sas = LegalEntity(
        name="Rupiv SAS",
        entity_type=EntityType.SAS,
        country_code="FR",
        vat_number="FR82123456789",
        registration_number="RCS-123456",
        default_currency="EUR",
        parent_id=parent.id,
    )
    session.add_all([gmbh, sas])
    await session.flush()
    log.info("entities_created", count=3)
    return [parent, gmbh, sas]


async def _seed_policy_rules(session: AsyncSession) -> list[PolicyRule]:
    """Insert 3 demo policy rules."""
    rules = [
        PolicyRule(
            name="Auto-approve small invoices",
            trigger="invoice.generated",
            conditions=[
                {"field": "invoice.total", "operator": "lt", "value": 5000},
            ],
            action="auto_approve",
            priority=10,
        ),
        PolicyRule(
            name="CFO approval for large invoices",
            trigger="invoice.generated",
            conditions=[
                {"field": "invoice.total", "operator": "gte", "value": 50000},
            ],
            action="require_approval",
            approver="cfo",
            escalation_after_hours=24,
            priority=20,
        ),
        PolicyRule(
            name="Reject low-CSAT outcomes",
            trigger="outcome.validated",
            conditions=[
                {"field": "properties.csat_score", "operator": "lt", "value": 2.0},
            ],
            action="reject",
            priority=5,
        ),
    ]
    session.add_all(rules)
    await session.flush()
    log.info("policy_rules_created", count=len(rules))
    return rules


async def _seed_quotes_and_contracts(
    session: AsyncSession,
    customers: list[Customer],
    plans: list[Plan],
    subs: list[Subscription],
) -> None:
    """Insert 2 quotes (one accepted with contract, one pending)."""
    plan_by_name: dict[str, Plan] = {p.name: p for p in plans}
    cust_by_ext: dict[str, Customer] = {c.external_id: c for c in customers}

    # Accepted quote for ResolvAI on Growth plan
    growth_plan = plan_by_name["Growth"]
    resolvai = cust_by_ext["cust_resolvai"]
    accepted_quote = Quote(
        customer_id=resolvai.id,
        plan_id=growth_plan.id,
        status=QuoteStatus.ACCEPTED,
        discount_pct=Decimal("10.00"),
        estimated_monthly=Decimal("350.0000"),
        estimated_total=Decimal("4200.0000"),
        currency="EUR",
        term_months=12,
        expires_at=_NOW + timedelta(days=30),
        accepted_at=_months_ago(3),
        notes="Growth plan with 10% annual commitment discount.",
    )
    session.add(accepted_quote)
    await session.flush()

    # Line items for accepted quote
    session.add_all([
        QuoteLineItem(
            quote_id=accepted_quote.id,
            description="Growth plan — monthly base fee",
            pricing_model="flat",
            unit_amount=Decimal("149.0000"),
            estimated_quantity=Decimal("1.0000"),
            estimated_amount=Decimal("149.0000"),
        ),
        QuoteLineItem(
            quote_id=accepted_quote.id,
            description="Usage: api_call (est. 20K/mo)",
            pricing_model="usage",
            metric="api_call",
            unit_amount=Decimal("0.1000"),
            estimated_quantity=Decimal("20.0000"),
            estimated_amount=Decimal("2.0000"),
        ),
        QuoteLineItem(
            quote_id=accepted_quote.id,
            description="Outcome: ticket_resolved (est. 200/mo)",
            pricing_model="outcome",
            metric="ticket_resolved",
            unit_amount=Decimal("0.9900"),
            estimated_quantity=Decimal("200.0000"),
            estimated_amount=Decimal("198.0000"),
        ),
    ])

    # Contract from accepted quote, linked to ResolvAI subscription
    resolvai_sub = next(s for s in subs if s.customer_id == resolvai.id)
    contract = Contract(
        quote_id=accepted_quote.id,
        subscription_id=resolvai_sub.id,
        start_date=_months_ago(3).date(),
        end_date=(_months_ago(3) + timedelta(days=365)).date(),
        term_months=12,
        renewal_type=ContractRenewalType.AUTO,
        early_termination_pct=Decimal("50.00"),
        status=ContractStatus.ACTIVE,
    )
    session.add(contract)

    # Pending quote for LegalMind on Scale plan
    scale_plan = plan_by_name["Scale"]
    legalmind = cust_by_ext["cust_legalmind"]
    pending_quote = Quote(
        customer_id=legalmind.id,
        plan_id=scale_plan.id,
        status=QuoteStatus.SENT,
        discount_pct=Decimal("5.00"),
        estimated_monthly=Decimal("800.0000"),
        estimated_total=Decimal("9600.0000"),
        currency="EUR",
        term_months=12,
        expires_at=_NOW + timedelta(days=14),
        notes="Upgrade proposal from Growth to Scale.",
    )
    session.add(pending_quote)
    await session.flush()

    session.add_all([
        QuoteLineItem(
            quote_id=pending_quote.id,
            description="Scale plan — monthly base fee",
            pricing_model="flat",
            unit_amount=Decimal("499.0000"),
            estimated_quantity=Decimal("1.0000"),
            estimated_amount=Decimal("499.0000"),
        ),
        QuoteLineItem(
            quote_id=pending_quote.id,
            description="Usage: api_call (est. 50K/mo)",
            pricing_model="usage",
            metric="api_call",
            unit_amount=Decimal("0.0600"),
            estimated_quantity=Decimal("50.0000"),
            estimated_amount=Decimal("3.0000"),
        ),
    ])
    await session.flush()
    log.info("quotes_created", count=2, contracts=1)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def seed(*, force: bool = False) -> None:
    """Run the full seed pipeline."""
    session_factory = _get_session_factory()

    async with session_factory() as session:
        await _ensure_tables(session)

        if not await _is_empty(session):
            if force:
                await _wipe(session)
            else:
                log.info(
                    "database_not_empty",
                    hint="Use --force to wipe and reseed.",
                )
                return

        log.info("seeding_started")

        customers = await _seed_customers(session)
        plans = await _seed_plans(session)
        subs = await _seed_subscriptions(session, customers, plans)
        events = await _seed_events(session, customers, subs)
        invoices = await _seed_invoices(session, customers, plans, subs)
        entities = await _seed_entities(session)
        policy_rules = await _seed_policy_rules(session)
        await _seed_quotes_and_contracts(session, customers, plans, subs)

        await session.commit()
        log.info(
            "seeding_complete",
            customers=len(customers),
            plans=len(plans),
            subscriptions=len(subs),
            events=len(events),
            invoices=len(invoices),
            entities=len(entities),
            policy_rules=len(policy_rules),
        )


def main() -> None:
    """CLI entry point — parse args and run the async seed."""
    parser = argparse.ArgumentParser(
        description="Seed the Rupiv.ai database with demo data.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Wipe existing data and reseed from scratch.",
    )
    args = parser.parse_args()
    asyncio.run(seed(force=args.force))


if __name__ == "__main__":
    main()
