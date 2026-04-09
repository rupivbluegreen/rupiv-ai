# CLAUDE.md — Rupiv.ai

> Outcome-based billing infrastructure for the agentic economy. EU-sovereign. Agent-native. Built for AI companies that charge for results, not seats.

---

## What is Rupiv.ai

Rupiv.ai is a billing OS that lets AI-native SaaS companies charge based on **outcomes delivered** (tickets resolved, tasks completed, fraud prevented) — not seats, not tokens, not API calls. It also supports usage-based and hybrid billing, plus **agent-to-agent (A2A) autonomous payments** via SEPA fiat rails for the emerging agentic economy.

Target customers: AI-native startups (Series A-C) in support AI, marketing AI, legal AI, DevOps AI — anyone whose product does autonomous work and needs to bill for results.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Language** | Python 3.12+ | Type-safe, async-first, LangGraph-native |
| **Framework** | FastAPI | Async REST + WebSocket, OpenAPI auto-docs |
| **Agent runtime** | LangGraph | Stateful billing agents, compliance agents, dunning agents |
| **Database** | PostgreSQL 16 + pgvector | Customers, plans, subscriptions, ledger, embeddings |
| **Analytics/metering** | ClickHouse | Sub-second aggregation on billions of usage events |
| **Queue** | BullMQ + Redis 7 | Async event processing, retries, dead-letter queues |
| **Payments** | Mollie (primary), Adyen EU (A2A SEPA) | EU-native PSPs, iDEAL + SEPA + cards |
| **Frontend** | React 18 + Vite + Tailwind | Dashboard, plan builder, analytics |
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
# Core development skills
claude skill install @anthropic/python-fastapi      # FastAPI patterns, async handlers
claude skill install @anthropic/pytest               # Testing patterns, fixtures, mocking
claude skill install @anthropic/docker               # Dockerfile, compose, multi-stage builds
claude skill install @anthropic/postgresql            # Schema design, migrations, queries
claude skill install @anthropic/sqlalchemy            # ORM patterns, async sessions
claude skill install @anthropic/redis                 # Caching, pub/sub, BullMQ patterns
claude skill install @anthropic/openapi               # API spec generation, validation

# AI/Agent skills
claude skill install @anthropic/langgraph             # State graphs, nodes, tools, checkpointing
claude skill install @anthropic/claude-api            # Claude SDK, structured outputs, tool use

# Frontend
claude skill install @anthropic/react                 # Components, hooks, state management
claude skill install @anthropic/tailwindcss            # Utility-first styling
claude skill install @anthropic/vite                   # Build config, HMR, env vars

# Infrastructure
claude skill install @anthropic/kubernetes             # Manifests, helm charts, operators
claude skill install @anthropic/opentelemetry          # Tracing, metrics, logging

# Quality
claude skill install @anthropic/ruff                   # Linting + formatting
claude skill install @anthropic/pyright                # Type checking
```

> **Note**: If a skill doesn't exist in the registry, Claude Code should still apply best practices for that technology. The above list represents the ideal skill set — use what's available and fall back to built-in knowledge for the rest.

---

## Project Structure

```
rupiv/
├── CLAUDE.md                    # This file
├── pyproject.toml               # uv/pip deps, ruff config, pyright config
├── Makefile                     # dev, test, lint, migrate, seed, docker-up
├── docker-compose.yml           # pg, redis, clickhouse, app
├── render.yaml                  # Render blueprint (Frankfurt)
│
├── src/
│   ├── rupiv/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app factory
│   │   ├── config.py            # Pydantic Settings, env vars
│   │   │
│   │   ├── api/                 # REST endpoints
│   │   │   ├── v1/
│   │   │   │   ├── events.py    # POST /v1/events — ingest usage/outcome events
│   │   │   │   ├── customers.py # CRUD customers
│   │   │   │   ├── plans.py     # Plan + pricing rule CRUD
│   │   │   │   ├── subscriptions.py
│   │   │   │   ├── invoices.py  # Invoice lifecycle
│   │   │   │   ├── webhooks.py  # Mollie/Adyen payment callbacks
│   │   │   │   └── a2a.py       # Agent-to-agent payment intents
│   │   │   └── middleware/
│   │   │       ├── auth.py      # API key + JWT validation
│   │   │       ├── rate_limit.py
│   │   │       └── tracing.py   # OTel span injection
│   │   │
│   │   ├── agents/              # LangGraph agent definitions
│   │   │   ├── billing_agent.py      # Metering → invoicing → charge
│   │   │   ├── dunning_agent.py      # Failed payment retry sequences
│   │   │   ├── compliance_agent.py   # GDPR/DORA/VAT checks
│   │   │   ├── outcome_agent.py      # Outcome validation + scoring
│   │   │   └── a2a_agent.py          # Agent-to-agent SEPA settlement
│   │   │
│   │   ├── billing/             # Core billing logic (no agent dependency)
│   │   │   ├── metering.py      # Event ingestion, ClickHouse writes
│   │   │   ├── aggregation.py   # Usage/outcome rollups per billing period
│   │   │   ├── pricing.py       # Pricing engine: flat, tiered, volume, outcome, hybrid
│   │   │   ├── invoicing.py     # Invoice generation, line items, EU VAT
│   │   │   ├── ledger.py        # Double-entry ledger for A2A
│   │   │   └── payment.py       # Mollie/Adyen charge execution
│   │   │
│   │   ├── models/              # SQLAlchemy models
│   │   │   ├── customer.py
│   │   │   ├── plan.py          # Plan + PricingRule (supports outcome metrics)
│   │   │   ├── subscription.py
│   │   │   ├── event.py         # UsageEvent + OutcomeEvent
│   │   │   ├── invoice.py
│   │   │   └── ledger.py        # LedgerEntry for A2A balances
│   │   │
│   │   ├── sdk/                 # Client SDKs (Python first, then Node/Go)
│   │   │   ├── python/
│   │   │   │   ├── rupiv/
│   │   │   │   │   ├── client.py
│   │   │   │   │   ├── events.py    # rupiv.track_outcome("ticket_resolved", {...})
│   │   │   │   │   └── types.py
│   │   │   │   └── pyproject.toml
│   │   │   └── README.md
│   │   │
│   │   └── workers/             # BullMQ consumers
│   │       ├── event_processor.py    # Dequeue events → ClickHouse
│   │       ├── invoice_worker.py     # Period-end invoice generation
│   │       └── payment_worker.py     # Charge execution + retry
│   │
│   └── migrations/              # Alembic
│       └── versions/
│
├── dashboard/                   # React frontend
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Overview.tsx     # MRR, ARR, churn, outcome metrics
│   │   │   ├── Customers.tsx
│   │   │   ├── Plans.tsx        # Visual plan builder with outcome rules
│   │   │   ├── Events.tsx       # Real-time event stream
│   │   │   └── Invoices.tsx
│   │   └── components/
│   └── vite.config.ts
│
└── tests/
    ├── conftest.py
    ├── test_metering.py
    ├── test_pricing.py          # Outcome pricing scenarios
    ├── test_invoicing.py
    ├── test_agents.py
    └── test_a2a.py
```

---

## Architecture — Outcome-Based Billing Flow

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
    │                                    │ ← event_processor writes to ClickHouse
    │                                    │ ← outcome_agent validates outcome
    │                                    │    (was it REALLY resolved? check rules)
    │                                    │
    │                               [Billing period end]
    │                                    │
    │                                    │ ← aggregation.py: rollup outcomes
    │                                    │ ← pricing.py: apply outcome pricing rules
    │                                    │    e.g. $0.99/resolved, $0/escalated
    │                                    │ ← invoicing.py: generate invoice
    │                                    │ ← billing_agent: decide charge timing
    │                                    │ ← payment.py: Mollie charge
    │                                    │
    │  Webhook: invoice.paid             │
    │ ←────────────────────────────────── │
```

---

## Pricing Engine — Supported Models

The pricing engine (`billing/pricing.py`) must support ALL of these on a single plan:

| Model | Charge Metric | Example |
|---|---|---|
| **Outcome-based** | Successful result delivered | $0.99/resolved ticket, $2.50/fraud prevented |
| **Usage-based** | Consumption volume | $0.001/API call, $0.01/1K tokens |
| **Hybrid** | Base + usage/outcome | $99/mo base + $0.50/resolution |
| **Tiered** | Volume brackets | 0-1K events: $0.01, 1K-10K: $0.008 |
| **Credit-based** | Pre-purchased credits | 10,000 credits for $500, 1 credit = 1 outcome |
| **Flat subscription** | Fixed recurring | $49/mo, $499/mo, $999/mo |

### Outcome Validation Rules

Outcomes need validation — customers will game the system otherwise. The `outcome_agent` applies rules:

```python
# Example outcome rule definition (stored in PricingRule)
{
    "metric": "ticket_resolved",
    "billable_when": {
        "escalated": False,           # Not escalated to human
        "resolution_time_lt": 300,    # Resolved in < 5 minutes
        "csat_score_gte": 3.0,        # Customer satisfaction ≥ 3/5
    },
    "price_per_outcome": 0.99,
    "cap_per_period": 50000,          # Max billable outcomes/month
}
```

---

## Agent-to-Agent (A2A) Payment Flow

For the agentic economy: AI agents that autonomously pay other AI agents.

```
Agent A (buyer)          Rupiv.ai A2A Rail           Agent B (seller)
───────────────          ─────────────────           ───────────────
      │                        │                           │
      │ POST /v1/a2a/intent    │                           │
      │ { from: agent_a_id,    │                           │
      │   to: agent_b_id,      │                           │
      │   amount: 12.50,       │                           │
      │   currency: EUR,       │                           │
      │   reason: "data_enrichment" }                      │
      │ ──────────────────────→│                           │
      │                        │ ← compliance_agent:       │
      │                        │   GDPR check, KYC, limits │
      │                        │ ← ledger.py:              │
      │                        │   reserve from A balance   │
      │                        │ ← SEPA credit transfer    │
      │                        │   via Adyen EU             │
      │                        │ ← ledger.py:              │
      │                        │   settle, credit B         │
      │                        │                           │
      │                        │ Webhook: payment.settled  │
      │                        │ ─────────────────────────→│
```

---

## Coding Rules

1. **Type hints everywhere** — all function signatures, return types, class attributes
2. **Dataclasses or Pydantic models** — never raw dicts for domain objects
3. **Async for all I/O** — database, HTTP, Redis, ClickHouse
4. **Single-responsibility modules** — one module, one concern
5. **Config via env vars** — `pydantic-settings` with `.env` support
6. **No print statements** — use `structlog` with JSON output
7. **Decimal for money** — never float. Use `decimal.Decimal` for all financial calculations
8. **Double-entry ledger** — every A2A transaction has debit + credit entries
9. **Idempotency keys** — all payment and event endpoints must be idempotent
10. **EU VAT logic** — reverse charge for B2B, standard rates for B2C, country detection

---

## Make Commands

```makefile
make dev          # docker-compose up + uvicorn --reload
make test         # pytest -x --tb=short
make lint         # ruff check + ruff format --check + pyright
make format       # ruff format + ruff check --fix
make migrate      # alembic upgrade head
make migration    # alembic revision --autogenerate -m "..."
make seed         # Load sample plans, customers, events
make sdk-build    # Build Python SDK wheel
make docker-build # Multi-stage Docker build
make deploy       # render deploy (via render.yaml blueprint)
```

---

## Gotchas

- **ClickHouse is append-only** — no UPDATEs. Design event schema for immutability. Use ReplacingMergeTree for deduplication.
- **Mollie webhooks are POST** — not GET. Verify via `X-Mollie-Signature` HMAC.
- **BullMQ in Python** — use `bullmq` Python package (not the Node.js one). It connects to the same Redis queues.
- **Outcome validation is async** — outcomes aren't billable until the outcome_agent confirms. Don't bill on ingest.
- **SEPA settlement is T+1** — A2A ledger entries are "pending" until Adyen confirms settlement. Don't release funds early.
- **Decimal precision** — PostgreSQL `NUMERIC(19,4)` for all money columns. ClickHouse `Decimal64(4)`.
- **Render free tier cold starts** — 30-50s spin-up. Set health check to `/health` with 60s timeout.
- **Never commit secrets** — use `.env.example` as template. Real secrets in Render dashboard.
- **EU VAT is complex** — use a library like `python-vatmoss` or build a lookup table. Don't hardcode rates.
- **Rate limiting on event ingestion** — ClickHouse can handle millions/sec but your API layer can't. Use BullMQ as buffer.

---

## MVP Scope (Weeks 1-8)

### Week 1-2: Foundation
- [ ] Project scaffolding (pyproject.toml, Docker, Makefile, CI)
- [ ] PostgreSQL schema: customers, plans, pricing_rules, subscriptions, events, invoices
- [ ] ClickHouse schema: events table (MergeTree, partitioned by day)
- [ ] FastAPI app factory with auth middleware, health check, OTel

### Week 3-4: Core Billing
- [ ] Event ingestion endpoint (`POST /v1/events`) — usage + outcome types
- [ ] BullMQ event processor → ClickHouse
- [ ] Pricing engine: flat, usage-based, outcome-based, hybrid
- [ ] Aggregation queries (ClickHouse → billing period rollups)
- [ ] Invoice generation with line items and EU VAT

### Week 5-6: Payments + Agents
- [ ] Mollie integration (charges, refunds, webhooks)
- [ ] Billing agent (LangGraph): meter → price → invoice → charge
- [ ] Dunning agent: retry sequence on failed payments
- [ ] Outcome agent: validate outcomes against pricing rules
- [ ] Python SDK: `rupiv.track_event()`, `rupiv.track_outcome()`

### Week 7-8: Dashboard + Polish
- [ ] React dashboard: overview (MRR/ARR), customers, plans, events, invoices
- [ ] Visual plan builder (drag-drop pricing rules)
- [ ] Real-time event stream (WebSocket)
- [ ] Render deployment (render.yaml, Frankfurt region)
- [ ] Landing page update with live demo
- [ ] API docs (auto-generated from OpenAPI)

### Post-MVP (Month 3-6)
- [ ] A2A payment rail (Adyen EU SEPA)
- [ ] Credit-based billing
- [ ] Node.js + Go SDKs
- [ ] Stripe integration (for US customers)
- [ ] Self-serve onboarding flow
- [ ] SOC 2 Type I prep

---

## Slash Commands

```
/scaffold     → Generate new module with tests, types, and docstring
/agent        → Create new LangGraph agent with state, nodes, tools
/endpoint     → Generate FastAPI endpoint with Pydantic models, auth, tests
/migration    → Generate Alembic migration from model changes
/test         → Generate pytest test file for a module
/pricing-rule → Generate a new pricing rule type with validation
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
