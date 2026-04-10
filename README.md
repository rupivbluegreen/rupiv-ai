<p align="center">
  <h1 align="center">Rupiv.ai</h1>
  <p align="center">
    <strong>The next-gen agentic billing platform.</strong>
  </p>
  <p align="center">
    Outcome-based pricing &middot; AI-native agents &middot; Quote-to-cash &middot; Developer-first
  </p>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="#features">Features</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#api-reference">API Reference</a> &middot;
  <a href="#sdks">SDKs</a> &middot;
  <a href="#deployment">Deployment</a>
</p>

---

## The Problem

AI agents are replacing human work. Per-seat billing is dying. **61% of SaaS companies** will use hybrid pricing models by 2026, but no billing platform natively supports outcome-based pricing, autonomous agent-to-agent payments, or AI-powered billing workflows.

Stripe has no concept of an "outcome." Chargebee tracks subscriptions. Zuora is enterprise legacy. None of them were built for the agentic economy.

## The Solution

Rupiv.ai is the **next-generation billing platform built for AI-native companies**. Charge for **results delivered** -- tickets resolved, fraud prevented, tasks completed -- not seats or API calls. Powered by 7 LangGraph agents that autonomously handle metering, invoicing, payment collection, dunning, compliance, quoting, and revenue recognition.

```python
import rupiv

client = rupiv.Client(api_key="rp_live_xxxxx")

# Track an outcome event
client.track_outcome(
    metric="ticket_resolved",
    customer_id="cust_abc123",
    properties={
        "resolution_time": 45,
        "csat_score": 4.8,
        "escalated": False,
    },
)
```

At billing period end, Rupiv.ai's **billing agent** validates the outcome, calculates the charge, applies tax rules, generates the invoice, collects payment, and creates the revenue schedule. Fully autonomous. No human in the loop.

---

## Features

### Billing Engine

| Model | Description | Example |
|---|---|---|
| **Outcome-based** | Charge per successful result | EUR 0.99/resolved ticket |
| **Usage-based** | Charge per consumption unit | EUR 0.001/API call |
| **Hybrid** | Base subscription + variable | EUR 99/mo + EUR 0.50/resolution |
| **Tiered** | Volume brackets | 0-1K: EUR 0.01, 1K-10K: EUR 0.008 |
| **Credit-based** | Pre-purchased credits | 10,000 credits for EUR 500 |
| **Flat** | Fixed recurring | EUR 49/mo |

All six models can be combined on a single plan.

### Outcome Validation

Outcomes are validated before billing. Define rules to prevent gaming:

```json
{
  "metric": "ticket_resolved",
  "billable_when": {
    "escalated": false,
    "resolution_time_lt": 300,
    "csat_score_gte": 3.0
  },
  "price_per_outcome": 0.99,
  "cap_per_period": 50000
}
```

### Tax Compliance

- **27 EU member state VAT rates** with automatic rate selection
- **B2B reverse charge** for cross-border intra-EU transactions
- **VIES validation** for EU VAT ID verification (async, cached)
- **One-Stop Shop (OSS)** for cross-border B2C with EUR 10K threshold
- **ViDA-ready** for 2028 real-time digital reporting mandate
- **Multi-region**: EU tax engine built-in, Stripe integration for US

### IFRS 15 Revenue Recognition

- Performance obligation identification (platform access, outcome delivery, usage)
- Transaction price allocation by standalone selling prices
- Revenue schedules: over-time for subscriptions, point-in-time for outcomes
- Variable consideration estimation using expected value method
- GL journal entry generation for accounting export

### Pricing Studio

- **What-if simulation**: replay historical events against new pricing rules
- **A/B test pricing**: deterministic customer assignment with conversion tracking
- **Revenue forecasting**: Monte Carlo projection with P10/P50/P90 bands
- **Pre-built templates**: Support AI, API Platform, Hybrid SaaS, Credit Pack

### Policy Engine

Declarative business rules for billing governance:

```yaml
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
```

### Multi-Entity

```
AcmeAI Corp
  |-- AcmeAI BV (NL) -- Holding, EUR
  |-- AcmeAI GmbH (DE) -- Subsidiary, EUR
  +-- AcmeAI Ltd (UK) -- Subsidiary, GBP
```

Multi-currency with ECB daily rates. Intercompany billing with transfer pricing.

### Agent-to-Agent Payments

The core of the agentic economy: AI agents that autonomously pay other AI agents. SEPA-native fiat rails via Adyen with a double-entry ledger and reserve-then-settle pattern. Compliance agent validates every transaction.

### Agentic Billing Agents

7 autonomous LangGraph agents handle billing operations without human intervention:

| Agent | Responsibility |
|---|---|
| **Billing Agent** | Metering -> pricing -> invoicing -> payment collection |
| **Outcome Agent** | Validates outcomes against billable_when rules and policy engine |
| **Dunning Agent** | Retries failed payments with configurable schedule (24h, 72h, 168h) |
| **Compliance Agent** | GDPR, VAT, amount limits, PSD2 checks on every transaction |
| **Quoting Agent** | Generates pricing proposals with policy-gated discount approval |
| **Revenue Agent** | IFRS 15 obligation identification, allocation, schedule generation |
| **A2A Agent** | Agent-to-agent SEPA settlement with ledger reserve-then-settle |

Each agent is a LangGraph `StateGraph` with typed state, async nodes, error handling, and checkpointing.

### Payment Integrations

| PSP | Region | Methods |
|---|---|---|
| **Mollie** | EU (primary) | iDEAL, SEPA DD, cards, Bancontact |
| **Stripe** | US expansion | Cards, ACH |
| **Adyen** | A2A SEPA | SEPA credit transfer |

Intelligent payment routing selects the cheapest PSP per transaction.

---

## Architecture

```
                    QUOTE-TO-CASH LIFECYCLE

  QUOTE -----> CONTRACT -----> USAGE -----> INVOICE
    |              |              |              |
  quoting      contract       metering      invoicing
  agent        terms, SLA     events to     line items,
                              ClickHouse    EU VAT
    |              |              |              |
    v              v              v              v
  SIMULATE     POLICY        VALIDATE        PAY
    |              |              |              |
  pricing      approval       outcome       Mollie/
  studio       gates          agent         Stripe
                                                |
                                                v
                                            REVENUE REC
                                                |
                                            IFRS 15
                                            schedules
```

### Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+, async-first |
| Framework | FastAPI (REST + WebSocket) |
| Agent Runtime | LangGraph (7 autonomous billing agents) |
| Database | PostgreSQL 16 |
| Analytics | ClickHouse |
| Queue | Redis 7 |
| Frontend | React 18 + Vite + Tailwind |
| ORM | SQLAlchemy 2.0 (async) |
| Payments | Mollie, Stripe, Adyen |

---

## Quickstart

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Node.js 20+ (for dashboard)

### 1. Clone and setup

```bash
git clone https://github.com/rupivbluegreen/rupiv.ai.git
cd rupiv.ai

# Create virtual environment and install dependencies
uv venv .venv --python 3.12
uv pip install -e "."
uv pip install ruff pyright pytest pytest-asyncio pytest-cov factory-boy faker

# Copy environment config
cp .env.example .env
```

### 2. Start infrastructure

```bash
# Start PostgreSQL, Redis, ClickHouse
docker compose up postgres redis clickhouse -d

# Run database migrations
make migrate

# Seed demo data (5 customers, 4 plans, ~200 events, invoices)
make seed
```

### 3. Run the API

```bash
make dev
# API available at http://localhost:8000
# OpenAPI docs at http://localhost:8000/docs
# ReDoc at http://localhost:8000/redoc
```

### 4. Run the dashboard

```bash
cd dashboard
npm install
npm run dev
# Dashboard at http://localhost:5173
```

### 5. Run tests

```bash
make test
# 386 tests passing
```

---

## API Reference

Base URL: `http://localhost:8000/v1`

### Events

```bash
# Track an outcome event
curl -X POST http://localhost:8000/v1/events \
  -H "X-API-Key: rp_live_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "outcome",
    "metric": "ticket_resolved",
    "customer_id": "550e8400-e29b-41d4-a716-446655440000",
    "properties": {
      "resolution_time": 45,
      "csat_score": 4.8,
      "escalated": false
    },
    "idempotency_key": "evt-unique-key-001"
  }'
```

### Core Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/v1/events` | Ingest usage/outcome events |
| GET/POST | `/v1/customers` | Customer management |
| GET/POST | `/v1/plans` | Plan and pricing rule CRUD |
| GET/POST | `/v1/subscriptions` | Subscription lifecycle |
| GET | `/v1/invoices` | Invoice listing and details |
| POST | `/v1/quotes` | Generate and manage quotes |
| GET | `/v1/revenue/schedules` | IFRS 15 revenue schedules |
| POST | `/v1/simulate` | Pricing simulation |
| GET | `/v1/analytics/mrr` | MRR/ARR metrics |
| POST | `/v1/a2a/intent` | Agent-to-agent payments |
| GET | `/v1/credits/{id}/balance` | Credit balance |
| POST | `/v1/onboarding/signup` | Self-serve signup |
| GET | `/v1/portal/me` | Customer self-service portal |
| GET | `/v1/portal/invoices` | Customer invoice viewing |
| GET | `/v1/portal/usage` | Customer usage dashboard |
| GET | `/v1/invoices/{id}/pdf` | PDF invoice download |
| GET | `/v1/alerts` | Revenue leakage alerts |
| POST | `/v1/alert-rules` | Alert rule management |
| GET | `/v1/erp/connections` | ERP integration management |
| POST | `/v1/erp/export` | Journal entry export (CSV/IIF/Xero) |
| GET | `/v1/transformations` | Data transformation rules |
| POST | `/v1/transformations/test` | Transformation preview |
| POST | `/v1/webhook-endpoints` | Outbound webhook management |

Full interactive documentation available at `/docs` when the API is running.

---

## SDKs

### Python

```bash
pip install rupiv-sdk
```

```python
import rupiv

client = rupiv.Client(api_key="rp_live_xxxxx")

# Track events
client.track_outcome("ticket_resolved", "cust_123", properties={"csat_score": 4.8})
client.track_event("api_call", "cust_123", properties={"tokens": 150})

# Quotes
quote = client.create_quote("cust_123", "plan_456", discount_pct=10, term_months=12)
client.accept_quote(quote.id)

# Credits
balance = client.get_credits("cust_123")
```

### Node.js / TypeScript

```bash
npm install @rupiv/sdk
```

```typescript
import { RupivClient } from '@rupiv/sdk';

const client = new RupivClient({ apiKey: 'rp_live_xxxxx' });

await client.trackOutcome({
  metric: 'ticket_resolved',
  customerId: 'cust_123',
  properties: { csatScore: 4.8 },
});

// High-throughput batching
import { EventBatcher } from '@rupiv/sdk';

const batcher = new EventBatcher({ apiKey: 'rp_live_xxxxx' });
batcher.addOutcome('ticket_resolved', 'cust_123', { csatScore: 4.8 });
// Auto-flushes at 100 events or 5 seconds
```

### Go

```bash
go get github.com/rupiv/rupiv-go
```

```go
client := rupiv.NewClient("rp_live_xxxxx")

resp, err := client.TrackOutcome(ctx, rupiv.TrackOutcomeParams{
    Metric:     "ticket_resolved",
    CustomerID: "cust_123",
    Properties: map[string]interface{}{"csat_score": 4.8},
})
```

---

## Dashboard

The React dashboard provides 16 pages for managing billing operations:

| Page | Description |
|---|---|
| **Overview** | MRR, ARR, outcome metrics, quick actions |
| **Customers** | Customer account management |
| **Entities** | Legal entity hierarchy with tree view |
| **Plans** | Visual plan builder with pricing rules |
| **Pricing Studio** | What-if simulation, forecasting, templates |
| **Quotes** | Quote pipeline (draft / sent / accepted / rejected) |
| **Events** | Real-time event stream with WebSocket |
| **Invoices** | Invoice lifecycle with status filtering + PDF download |
| **Revenue** | IFRS 15 schedules, journal entries, waterfall chart |
| **Policies** | Policy rule builder with outcome validator |
| **Payment Analytics** | PSP cost comparison, routing recommendations |
| **Alerts** | Revenue leakage detection, anomaly alerts |
| **ERP Export** | Journal entry export to QuickBooks, Xero, CSV |
| **Transformations** | Visual data transformation rules with preview |
| **Onboarding** | Self-serve signup wizard |
| **Customer Portal** | Self-service invoices, usage, subscription (separate layout) |

---

## Project Structure

```
rupiv.ai/
  src/rupiv/
    api/v1/          18 endpoint modules
    agents/           7 LangGraph agents
    billing/         11 billing engine modules
    tax/              6 EU VAT modules
    policy/           5 policy engine modules
    entities/         5 multi-entity modules
    revenue_recognition/  6 IFRS 15 modules
    pricing_studio/   5 simulation modules
    quoting/          4 quote-to-cash modules
    analytics/        6 business analytics modules
    compliance/       3 audit + GDPR modules
    models/          21 SQLAlchemy models
    workers/          9 background workers
    erp/              ERP export formatters
    invoicing/        PDF invoice generation
    transformations/  Data transformation engine
    webhooks/         Outbound webhook dispatch
    sdk/              Python, Node.js, Go SDKs
  dashboard/         16 pages, 12 components
  tests/             43 test files, 386 tests
  migrations/        16 Alembic migrations
```

---

## Deployment

### Docker

```bash
# Build and run all services
docker compose up --build

# Services:
# - app: FastAPI API on port 8000
# - worker: BullMQ event processor
# - postgres: PostgreSQL 16 on port 5432
# - redis: Redis 7 on port 6379
# - clickhouse: ClickHouse on ports 8123/9000
```

### Render (Production)

The project includes a `render.yaml` blueprint for one-click deployment:

```bash
make deploy
```

### Environment Variables

See `.env.example` for all configuration options. Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `CLICKHOUSE_URL` | ClickHouse HTTP endpoint |
| `MOLLIE_API_KEY` | Mollie payment API key |
| `STRIPE_API_KEY` | Stripe API key (US payments) |
| `ADYEN_API_KEY` | Adyen API key (A2A SEPA) |
| `APP_SECRET_KEY` | Application secret for JWT signing |

---

## Development

```bash
make dev            # Start all services + hot reload
make test           # Run 386 tests
make lint           # ruff check + format check
make format         # Auto-format code
make migrate        # Run database migrations
make seed           # Load demo data
make seed-simulate  # Demo data + pricing simulation
make vat-update     # Refresh EU VAT rates
make docker-build   # Build production Docker image
```

### CI/CD

GitHub Actions runs on every push:
1. **Lint** -- ruff check + format
2. **Test** -- pytest with coverage
3. **Frontend** -- TypeScript check + Vite build
4. **Docker** -- Build image + health check

---

## Security

- **API key authentication** on all endpoints (SHA-256 hashed, `secrets.token_hex` generated)
- **Clerk JWT verification** with JWKS rotation for portal authentication
- **HMAC-SHA256 webhook signatures** for both inbound (Mollie/Stripe) and outbound delivery
- **SSRF protection** on webhook URL registration (blocks private IPs, cloud metadata)
- **Safe expression evaluator** (AST-based, no `eval()`) for data transformation rules
- **Rate limiting** per API key (100 req/min default, 1000 for events)
- **Audit logging** on all write operations + reads on sensitive resources
- **PII-free structured logs** (no emails, names, or payment data in log output)
- **Infrastructure hardening**: Redis auth, localhost-only port binding, env-based credentials
- **GDPR Article 17 + 20**: data export and anonymization endpoints
- **PCI DSS compliant**: no raw card data stored; PSP tokens only

---

## Competitive Landscape

|  | Outcome Billing | EU VAT | IFRS 15 | Pricing Studio | A2A Payments | Policy Engine |
|---|---|---|---|---|---|---|
| Stripe Billing | -- | Partial | -- | -- | -- | -- |
| Chargebee | -- | Partial | -- | -- | -- | -- |
| Lago | Basic usage | -- | -- | -- | -- | -- |
| Orb | Usage only | -- | -- | -- | -- | -- |
| Flexprice | Partial | -- | -- | -- | -- | -- |
| **Rupiv.ai** | **Full** | **Full** | **Full** | **Full** | **Full** | **Full** |

---

## License

Proprietary. All rights reserved.

---

<p align="center">
  Built for the agentic economy. Headquartered in Delft, Netherlands.
</p>
