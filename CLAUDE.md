# CLAUDE.md — Rupiv.ai

> Outcome-based billing infrastructure for AI companies selling into Europe. EU VAT + IFRS 15 + GDPR baked in. Developer-first. Agent-native.

---

## What is Rupiv.ai

Rupiv.ai is a billing OS that lets AI-native SaaS companies charge based on **outcomes delivered** (tickets resolved, tasks completed, fraud prevented) — not seats, not tokens, not API calls. It also supports usage-based, hybrid, and credit-based billing, plus **agent-to-agent (A2A) autonomous payments** via SEPA fiat rails.

**EU-first positioning**: Every AI company selling into Europe hits the same wall — EU VAT across 27 member states, IFRS 15 revenue recognition for variable pricing, GDPR data residency, ViDA real-time reporting. Rupiv.ai handles all of it out of the box.

**Target customers**: AI-native startups (Seed–Series C) in support AI, marketing AI, legal AI, DevOps AI, fraud detection — anyone whose product does autonomous work and needs to bill for results in Europe.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Language** | Python 3.12+ | Type-safe, async-first, LangGraph-native |
| **Framework** | FastAPI | Async REST + WebSocket, OpenAPI auto-docs |
| **Agent runtime** | LangGraph | Stateful billing, compliance, dunning, quoting agents |
| **Database** | PostgreSQL 16 + pgvector | Customers, plans, subscriptions, ledger, entities, embeddings |
| **Analytics/metering** | ClickHouse | Sub-second aggregation on billions of usage/outcome events |
| **Queue** | BullMQ + Redis 7 | Async event processing, retries, dead-letter queues |
| **Payments** | Mollie (primary), Adyen EU (A2A SEPA) | EU-native PSPs, iDEAL + SEPA + cards |
| **Frontend** | React 18 + Vite + Tailwind | Dashboard, Pricing Studio, analytics |
| **ORM** | SQLAlchemy 2.0 (async) | Not Prisma — keep everything Python-native |
| **Auth** | Clerk or Auth0 | JWT + API keys for SDK auth |
| **Infra** | Docker → Render (MVP) → Kubernetes (scale) | Start simple, migrate when needed |
| **Observability** | OpenTelemetry + W3C Trace Context | Distributed tracing across billing pipeline |
| **Testing** | pytest + pytest-asyncio | 80%+ coverage target |

### Removed from stack (lessons from Pave)
- ~~n8n~~ — Adds operational overhead, duplicates capabilities, reduces debuggability. All integrations are native Python.
- ~~Prisma~~ — Node.js dependency in a Python project. Use SQLAlchemy async.

---

## Claude Code Skills to Install

```bash
# Core development
claude skill install @anthropic/python-fastapi
claude skill install @anthropic/pytest
claude skill install @anthropic/docker
claude skill install @anthropic/postgresql
claude skill install @anthropic/sqlalchemy
claude skill install @anthropic/redis
claude skill install @anthropic/openapi

# AI/Agent
claude skill install @anthropic/langgraph
claude skill install @anthropic/claude-api

# Frontend
claude skill install @anthropic/react
claude skill install @anthropic/tailwindcss
claude skill install @anthropic/vite

# Infrastructure
claude skill install @anthropic/kubernetes
claude skill install @anthropic/opentelemetry

# Quality
claude skill install @anthropic/ruff
claude skill install @anthropic/pyright
```

> **Note**: If a skill doesn't exist in the registry, Claude Code should still apply best practices for that technology. Use what's available and fall back to built-in knowledge for the rest.

---

## Project Structure

```
rupiv/
├── CLAUDE.md
├── pyproject.toml
├── Makefile
├── docker-compose.yml
├── render.yaml                          # Render blueprint (Frankfurt)
│
├── src/
│   ├── rupiv/
│   │   ├── __init__.py
│   │   ├── main.py                      # FastAPI app factory
│   │   ├── config.py                    # Pydantic Settings, env vars
│   │   │
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── events.py            # POST /v1/events — ingest usage/outcome events
│   │   │   │   ├── customers.py         # CRUD customers
│   │   │   │   ├── entities.py          # Multi-entity management (BV, GmbH, SAS)
│   │   │   │   ├── plans.py             # Plan + pricing rule CRUD
│   │   │   │   ├── subscriptions.py
│   │   │   │   ├── invoices.py          # Invoice lifecycle
│   │   │   │   ├── quotes.py            # Quote generation + acceptance
│   │   │   │   ├── revenue.py           # IFRS 15 revenue schedules
│   │   │   │   ├── webhooks.py          # Mollie/Adyen payment callbacks
│   │   │   │   ├── a2a.py              # Agent-to-agent payment intents
│   │   │   │   ├── simulate.py          # Pricing Studio simulation endpoint
│   │   │   │   └── analytics.py         # Payment cost analytics
│   │   │   └── middleware/
│   │   │       ├── auth.py
│   │   │       ├── rate_limit.py
│   │   │       └── tracing.py
│   │   │
│   │   ├── agents/                      # LangGraph agent definitions
│   │   │   ├── billing_agent.py         # Metering → invoicing → charge
│   │   │   ├── dunning_agent.py         # Failed payment retry sequences
│   │   │   ├── compliance_agent.py      # GDPR/DORA/VAT checks
│   │   │   ├── outcome_agent.py         # Outcome validation + scoring
│   │   │   ├── quoting_agent.py         # Generate pricing proposals from prospect data
│   │   │   ├── revenue_agent.py         # IFRS 15 schedule generation + adjustments
│   │   │   └── a2a_agent.py             # Agent-to-agent SEPA settlement
│   │   │
│   │   ├── billing/                     # Core billing logic (no agent dependency)
│   │   │   ├── metering.py              # Event ingestion, ClickHouse writes
│   │   │   ├── aggregation.py           # Usage/outcome rollups per billing period
│   │   │   ├── pricing.py              # Pricing engine: flat, tiered, volume, outcome, hybrid
│   │   │   ├── invoicing.py             # Invoice generation, line items, EU VAT
│   │   │   ├── ledger.py               # Double-entry ledger for A2A
│   │   │   ├── payment.py              # Mollie/Adyen charge execution
│   │   │   └── payment_routing.py       # Cheapest PSP route per transaction type
│   │   │
│   │   ├── quoting/                     # Quote-to-Cash lifecycle
│   │   │   ├── quote_builder.py         # Generate quotes from plan templates + prospect context
│   │   │   ├── quote_acceptance.py      # Accept → create subscription + schedule
│   │   │   └── contract.py             # Contract terms, renewal rules, SLA definitions
│   │   │
│   │   ├── pricing_studio/             # No-code pricing simulation engine
│   │   │   ├── simulator.py             # Run pricing scenarios against historical data
│   │   │   ├── ab_test.py              # A/B test pricing models on live traffic
│   │   │   ├── revenue_forecast.py      # Project revenue impact of pricing changes
│   │   │   └── templates.py            # Pre-built pricing templates (outcome, hybrid, credit)
│   │   │
│   │   ├── policy/                      # Declarative business rules engine
│   │   │   ├── engine.py               # Evaluate policy rules against events/invoices
│   │   │   ├── rules.py                # Rule definitions (YAML/JSON → Python)
│   │   │   ├── approvals.py            # Approval workflows (auto/manual/escalation)
│   │   │   └── thresholds.py           # Spending limits, discount caps, outcome caps
│   │   │
│   │   ├── revenue_recognition/        # IFRS 15 compliance
│   │   │   ├── obligations.py           # Performance obligation identification
│   │   │   ├── allocation.py           # Transaction price allocation
│   │   │   ├── schedules.py            # Revenue schedule generation (point-in-time vs over-time)
│   │   │   ├── variable_consideration.py # Estimate variable fees from outcome billing
│   │   │   └── journal.py             # GL journal entries for accounting export
│   │   │
│   │   ├── tax/                         # EU VAT engine
│   │   │   ├── vat_engine.py            # Rate lookup, B2B reverse charge, B2C destination
│   │   │   ├── vat_id_validation.py     # VIES API validation for EU VAT IDs
│   │   │   ├── vida.py                 # ViDA real-time digital reporting (2028-ready)
│   │   │   ├── oss.py                  # One-Stop Shop for cross-border B2C
│   │   │   └── rates.py               # EU27 VAT rate table (auto-updated)
│   │   │
│   │   ├── entities/                    # Multi-entity / multi-currency
│   │   │   ├── entity.py               # Legal entity model (BV, GmbH, SAS, Ltd)
│   │   │   ├── hierarchy.py            # Parent-child entity trees
│   │   │   ├── intercompany.py         # Intercompany billing + reconciliation
│   │   │   └── currency.py            # Multi-currency with ECB daily rates
│   │   │
│   │   ├── analytics/                   # Payment cost + business analytics
│   │   │   ├── payment_costs.py         # Blended cost per PSP per transaction type
│   │   │   ├── routing_optimizer.py     # Recommend cheapest payment route
│   │   │   ├── mrr_arr.py             # MRR, ARR, churn, expansion, contraction
│   │   │   ├── outcome_metrics.py      # Outcome success rate, avg value, validation rate
│   │   │   └── cohort.py              # Customer cohort analysis
│   │   │
│   │   ├── models/                      # SQLAlchemy models
│   │   │   ├── customer.py
│   │   │   ├── entity.py               # LegalEntity, EntityHierarchy
│   │   │   ├── plan.py                 # Plan + PricingRule (supports outcome metrics)
│   │   │   ├── subscription.py
│   │   │   ├── event.py                # UsageEvent + OutcomeEvent
│   │   │   ├── invoice.py
│   │   │   ├── quote.py               # Quote, QuoteLineItem, QuoteStatus
│   │   │   ├── contract.py            # Contract, ContractTerm, RenewalRule
│   │   │   ├── ledger.py              # LedgerEntry for A2A balances
│   │   │   ├── revenue_schedule.py     # IFRS 15 RevenueSchedule, RevenueEntry
│   │   │   ├── policy_rule.py         # PolicyRule, ApprovalWorkflow
│   │   │   └── payment_cost.py        # PaymentCostRecord per PSP
│   │   │
│   │   ├── sdk/                        # Client SDKs
│   │   │   ├── python/
│   │   │   │   ├── rupiv/
│   │   │   │   │   ├── client.py
│   │   │   │   │   ├── events.py       # rupiv.track_outcome("ticket_resolved", {...})
│   │   │   │   │   ├── quotes.py      # rupiv.create_quote(prospect_id, plan_id)
│   │   │   │   │   └── types.py
│   │   │   │   └── pyproject.toml
│   │   │   └── README.md
│   │   │
│   │   └── workers/                    # BullMQ consumers
│   │       ├── event_processor.py       # Dequeue events → ClickHouse
│   │       ├── invoice_worker.py        # Period-end invoice generation
│   │       ├── payment_worker.py        # Charge execution + retry
│   │       ├── revenue_worker.py        # IFRS 15 schedule recalculation
│   │       ├── vat_worker.py           # Async VAT ID validation via VIES
│   │       └── simulation_worker.py    # Background pricing simulations
│   │
│   └── migrations/
│       └── versions/
│
├── dashboard/                           # React frontend
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Overview.tsx             # MRR, ARR, churn, outcome metrics
│   │   │   ├── Customers.tsx
│   │   │   ├── Entities.tsx            # Legal entity hierarchy manager
│   │   │   ├── Plans.tsx               # Visual plan builder with outcome rules
│   │   │   ├── PricingStudio.tsx       # Simulation sandbox (what-if scenarios)
│   │   │   ├── Quotes.tsx             # Quote pipeline (draft → sent → accepted)
│   │   │   ├── Events.tsx             # Real-time event stream
│   │   │   ├── Invoices.tsx
│   │   │   ├── Revenue.tsx            # IFRS 15 revenue schedules + waterfall
│   │   │   ├── Policies.tsx           # Policy rule builder (visual)
│   │   │   └── PaymentAnalytics.tsx   # PSP cost comparison + routing
│   │   └── components/
│   │       ├── PricingSimulator.tsx    # Interactive pricing scenario builder
│   │       ├── PolicyBuilder.tsx      # Drag-drop policy rule editor
│   │       ├── EntityTree.tsx         # Visual entity hierarchy
│   │       ├── RevenueWaterfall.tsx   # IFRS 15 waterfall chart
│   │       └── OutcomeValidator.tsx   # Visual outcome rule tester
│   └── vite.config.ts
│
└── tests/
    ├── conftest.py
    ├── test_metering.py
    ├── test_pricing.py
    ├── test_outcome_validation.py
    ├── test_invoicing.py
    ├── test_vat_engine.py
    ├── test_ifrs15.py
    ├── test_policy_engine.py
    ├── test_pricing_studio.py
    ├── test_quoting.py
    ├── test_entities.py
    ├── test_payment_routing.py
    ├── test_agents.py
    └── test_a2a.py
```

---

## Architecture — Full Quote-to-Cash Flow

```
                    QUOTE-TO-CASH LIFECYCLE
                    ═══════════════════════

  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │  QUOTE   │───→│ CONTRACT │───→│  USAGE   │───→│ INVOICE  │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
       │               │               │               │
  quoting_agent   contract.py    metering.py     invoicing.py
  generates       terms, SLA,    events stream   line items,
  proposal from   renewal rules  to ClickHouse   EU VAT calc
  plan + prospect                                     │
       │               │               │               │
       ▼               ▼               ▼               ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ SIMULATE │    │  POLICY  │    │ VALIDATE │    │   PAY    │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
       │               │               │               │
  pricing_studio  policy engine   outcome_agent   payment.py
  what-if on      approval gates  was it REALLY   Mollie/Adyen
  revenue impact  thresholds      resolved?       cheapest route
                  escalation                           │
                                                       ▼
                                                 ┌──────────┐
                                                 │ REVENUE  │
                                                 │   REC    │
                                                 └──────────┘
                                                       │
                                                 revenue_agent
                                                 IFRS 15 schedule
                                                 journal entries
                                                 variable consideration
```

---

## Outcome-Based Billing Flow (Detail)

```
Customer's AI agent                  Rupiv.ai
─────────────────                    ────────
    │                                    │
    │  POST /v1/events                   │
    │  { type: "outcome",                │
    │    metric: "ticket_resolved",      │
    │    properties: {                   │
    │      resolution_time: 45,          │
    │      escalated: false,             │
    │      csat_score: 4.8 }}            │
    │ ──────────────────────────────────→ │
    │                                    │ ← BullMQ queue
    │                                    │ ← event_processor → ClickHouse
    │                                    │ ← outcome_agent validates:
    │                                    │    - policy rules pass?
    │                                    │    - within threshold caps?
    │                                    │    - approval required?
    │                                    │
    │                               [Billing period end]
    │                                    │
    │                                    │ ← aggregation.py: rollup outcomes
    │                                    │ ← pricing.py: apply outcome rules
    │                                    │ ← vat_engine.py: EU VAT per line
    │                                    │ ← invoicing.py: generate invoice
    │                                    │ ← policy engine: auto-approve?
    │                                    │ ← payment_routing: cheapest PSP
    │                                    │ ← payment.py: Mollie charge
    │                                    │ ← revenue_agent: IFRS 15 schedule
    │                                    │
    │  Webhook: invoice.paid             │
    │ ←────────────────────────────────── │
```

---

## Pricing Engine — Supported Models

| Model | Charge Metric | Example |
|---|---|---|
| **Outcome-based** | Successful result delivered | €0.99/resolved ticket, €2.50/fraud prevented |
| **Usage-based** | Consumption volume | €0.001/API call, €0.01/1K tokens |
| **Hybrid** | Base + usage/outcome | €99/mo base + €0.50/resolution |
| **Tiered** | Volume brackets | 0-1K events: €0.01, 1K-10K: €0.008 |
| **Credit-based** | Pre-purchased credits | 10,000 credits for €500, 1 credit = 1 outcome |
| **Flat subscription** | Fixed recurring | €49/mo, €499/mo, €999/mo |

### Outcome Validation Rules

```python
# Example outcome rule (stored in PricingRule model)
{
    "metric": "ticket_resolved",
    "billable_when": {
        "escalated": False,
        "resolution_time_lt": 300,
        "csat_score_gte": 3.0,
    },
    "price_per_outcome": 0.99,
    "cap_per_period": 50000,
    "currency": "EUR",
}
```

---

## Pricing Studio — Simulation Engine

### Core Capabilities

1. **What-If Scenarios**: "If I change from €0.99/resolution to €1.50 with CSAT ≥ 4.0, what happens to revenue?"
2. **A/B Test Pricing**: Split live traffic between pricing models
3. **Revenue Forecasting**: Monte Carlo simulation using historical distributions
4. **Pre-built Templates**: One-click starting points for common AI billing patterns

### Simulation API

```python
# POST /v1/simulate
{
    "plan_id": "plan_abc123",
    "scenario": {
        "pricing_rules": [
            {
                "metric": "ticket_resolved",
                "price_per_outcome": 1.50,
                "billable_when": {"csat_score_gte": 4.0, "escalated": false}
            }
        ],
        "date_range": {"start": "2026-01-01", "end": "2026-03-31"}
    }
}
```

---

## Policy Engine — Declarative Business Rules

```yaml
# policies/invoice_approval.yaml
rules:
  - name: "Auto-approve small invoices"
    trigger: "invoice.generated"
    conditions:
      - field: "invoice.total"
        operator: "lt"
        value: 5000
    action: "auto_approve"

  - name: "CFO approval for large invoices"
    trigger: "invoice.generated"
    conditions:
      - field: "invoice.total"
        operator: "gte"
        value: 50000
    action: "require_approval"
    approver: "cfo"
    escalation_after_hours: 24
```

---

## IFRS 15 Revenue Recognition

Outcome-based billing creates accounting complexity. IFRS 15 5-step model:

1. **Identify contract** → `contract.py`
2. **Identify performance obligations** → `obligations.py`
3. **Determine transaction price** → `allocation.py` (variable consideration for outcome billing)
4. **Allocate to obligations** → `allocation.py`
5. **Recognize on satisfaction** → `schedules.py`

---

## EU VAT Engine

| Feature | Description |
|---|---|
| **B2B reverse charge** | Valid EU VAT ID → 0% + reverse charge note |
| **B2C destination** | Customer country → local VAT rate |
| **VIES validation** | Real-time VAT ID check via EU VIES API (async) |
| **OSS** | Cross-border B2C aggregation for single-country filing |
| **ViDA readiness** | Real-time digital reporting format (mandatory 2028) |
| **Rate table** | EU27 standard + reduced rates, auto-updated quarterly |

---

## Multi-Entity / Multi-Currency

```
Customer: "AcmeAI Corp"
    │
    ├── AcmeAI BV (NL) ← Holding, EUR, NL123456789B01
    ├── AcmeAI GmbH (DE) ← Sub, EUR, DE123456789
    └── AcmeAI Ltd (UK) ← Sub, GBP, GB123456789
```

Intercompany: When GmbH customers use BV infrastructure, Rupiv.ai auto-generates intercompany invoices with transfer pricing.

---

## Coding Rules

1. **Type hints everywhere** — all signatures, returns, attributes
2. **Dataclasses or Pydantic** — never raw dicts for domain objects
3. **Async for all I/O** — database, HTTP, Redis, ClickHouse
4. **Single-responsibility modules** — one module, one concern
5. **Config via env vars** — `pydantic-settings` with `.env`
6. **No print** — `structlog` with JSON output
7. **Decimal for money** — never float. `decimal.Decimal` everywhere.
8. **Double-entry ledger** — every A2A tx has debit + credit
9. **Idempotency keys** — all payment/event endpoints
10. **EU VAT** — reverse charge B2B, destination B2C
11. **IFRS 15 by default** — every invoice triggers revenue schedule
12. **Policy-aware** — all state transitions pass through policy engine

---

## Make Commands

```makefile
make dev            # docker-compose up + uvicorn --reload
make test           # pytest -x --tb=short
make lint           # ruff check + ruff format --check + pyright
make format         # ruff format + ruff check --fix
make migrate        # alembic upgrade head
make migration      # alembic revision --autogenerate -m "..."
make seed           # Sample plans, customers, events, policies
make seed-simulate  # Sample data + pricing simulation demo
make sdk-build      # Build Python SDK wheel
make docker-build   # Multi-stage Docker build
make deploy         # render deploy (render.yaml)
make vat-update     # Refresh EU VAT rates from EC database
```

---

## Gotchas

- **ClickHouse is append-only** — no UPDATEs. ReplacingMergeTree for dedup.
- **Mollie webhooks are POST** — verify `X-Mollie-Signature` HMAC.
- **BullMQ in Python** — `bullmq` Python package, not Node.js.
- **Outcome validation is async** — don't bill on ingest, wait for agent confirmation.
- **SEPA settlement is T+1** — A2A entries "pending" until Adyen confirms.
- **Decimal precision** — PG `NUMERIC(19,4)`, ClickHouse `Decimal64(4)`.
- **Render cold starts** — 30-50s. Health check `/health` 60s timeout.
- **Never commit secrets** — `.env.example` template only.
- **VIES API downtime** — cache validations 24h, queue retries.
- **IFRS 15 variable consideration** — constrain conservatively, log all assumptions.
- **Multi-currency rounding** — round per line item, not totals.
- **Policy rule ordering** — priority order. First `reject` wins.

---

## MVP Scope (Weeks 1-10)

### Week 1-2: Foundation
- [ ] Scaffolding (pyproject.toml, Docker, Makefile, CI)
- [ ] PG schema: customers, entities, plans, pricing_rules, subscriptions, events, invoices, quotes, contracts, policies, revenue_schedules
- [ ] ClickHouse: events (MergeTree, partition by day)
- [ ] FastAPI app factory + auth + health + OTel
- [ ] Policy engine core (YAML rules, evaluation, approval states)

### Week 3-4: Core Billing + EU VAT
- [ ] Event ingestion (`POST /v1/events`)
- [ ] BullMQ processor → ClickHouse
- [ ] Pricing engine: flat, usage, outcome, hybrid
- [ ] EU VAT: rates, B2B reverse charge, VIES
- [ ] Aggregation (ClickHouse rollups)
- [ ] Invoicing with EU VAT + sequential numbering

### Week 5-6: Agents + Outcome Validation
- [ ] Mollie integration
- [ ] Billing agent (LangGraph)
- [ ] Outcome agent + policy engine integration
- [ ] Dunning agent
- [ ] Python SDK

### Week 7-8: Pricing Studio + Policies
- [ ] What-if simulation against historical data
- [ ] Simulation API (`POST /v1/simulate`)
- [ ] Revenue forecasting (Monte Carlo)
- [ ] Policy builder UI
- [ ] Pre-built pricing templates (4)

### Week 9-10: Dashboard + RevRec + Launch
- [ ] React dashboard (overview, customers, plans, events, invoices)
- [ ] Pricing Studio UI
- [ ] IFRS 15 revenue schedules (basic)
- [ ] Revenue waterfall chart
- [ ] Render deploy (Frankfurt)
- [ ] Landing page + API docs

### Post-MVP

| Month | Feature | Priority |
|---|---|---|
| 4 | Quoting agent (quote-to-cash upstream) | P1 |
| 5 | IFRS 15 variable consideration | P1 |
| 5 | A/B test pricing live | P1 |
| 6 | Multi-entity + intercompany | P2 |
| 6 | Node.js + Go SDKs | P2 |
| 7 | Multi-currency (ECB rates) | P2 |
| 8 | Payment cost analytics + routing | P2 |
| 9 | A2A agent payments (SEPA) | P2 |
| 10 | ViDA reporting (2028-ready) | P2 |
| 10 | Credit-based billing | P2 |
| 11 | Stripe integration (US expansion) | P3 |
| 12 | Self-serve onboarding + SOC 2 Type I | P3 |

---

## Slash Commands

```
/scaffold       → New module with tests, types, docstring
/agent          → New LangGraph agent with state, nodes, tools
/endpoint       → FastAPI endpoint with Pydantic, auth, tests
/migration      → Alembic migration from model changes
/test           → Pytest test file for a module
/pricing-rule   → New pricing rule type with validation
/policy-rule    → New policy rule with conditions and actions
/simulate       → Run pricing simulation against seed data
/vat-scenario   → EU VAT test scenario (B2B/B2C, cross-border)
/ifrs15         → IFRS 15 revenue schedule for a subscription
```

---

## PostToolUse Hooks

```yaml
# .claude/hooks.yaml
post_tool_use:
  - tool: create_file
    pattern: "src/rupiv/**/*.py"
    run: "ruff check {file} && pyright {file}"
  - tool: str_replace
    pattern: "src/rupiv/**/*.py"
    run: "ruff check {file}"
  - tool: create_file
    pattern: "tests/**/*.py"
    run: "pytest {file} -x --tb=short 2>/dev/null || true"
```
