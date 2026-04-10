# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Rupiv.ai

Outcome-based billing infrastructure for AI companies selling into Europe. Supports outcome-based, usage-based, hybrid, tiered, credit-based, and flat subscription pricing. EU VAT (27 member states), IFRS 15 revenue recognition, and GDPR compliance built in. Agent-to-agent (A2A) autonomous payments via SEPA fiat rails.

## Commands

All Python tooling uses **uv** (not pip/poetry). The `Makefile` wraps everything:

```bash
make dev              # docker compose up --build (app, worker, postgres, redis, clickhouse)
make test             # pytest with coverage (uses in-memory SQLite, no external services needed)
make lint             # ruff check + ruff format --check + pyright (strict mode)
make format           # ruff format + ruff check --fix
make migrate          # alembic upgrade head
make migration msg="description"  # alembic revision --autogenerate
make seed             # seed sample data
```

Run a single test file or test:
```bash
uv run pytest tests/test_pricing.py -x --tb=short
uv run pytest tests/test_pricing.py::test_outcome_pricing -x --tb=short
```

Dashboard (React):
```bash
cd dashboard && npm run dev    # Vite dev server on :5173
cd dashboard && npm run build  # tsc + vite build
cd dashboard && npm run lint   # eslint
```

## Architecture

### Backend (Python 3.12+ / FastAPI)

**Entry point**: `src/rupiv/main.py` — `create_app()` factory with async lifespan managing PG, Redis, ClickHouse connections. Redis and ClickHouse are optional in dev (app continues without them).

**Config**: `src/rupiv/config.py` — Pydantic Settings loaded from env vars / `.env`. Key: `DATABASE_URL`, `REDIS_URL`, `CLICKHOUSE_URL`, `MOLLIE_API_KEY`, `ADYEN_API_KEY`, `STRIPE_API_KEY`, `CLERK_SECRET_KEY`.

**Database**: `src/rupiv/db.py` — SQLAlchemy 2.0 async with `Base` declarative model (UUID PKs, `created_at`/`updated_at` columns on all tables). Naming convention enforced for Alembic deterministic migrations.

**API layer**: All routes under `src/rupiv/api/v1/` aggregated into `v1_router` (prefix `/v1`). Endpoints: events, customers, entities, plans, subscriptions, invoices, quotes, revenue, credits, analytics, simulate, a2a, webhooks, api-keys, onboarding, compliance, stream, docs.

**Core billing logic** (no agent dependency): `src/rupiv/billing/` — metering, aggregation, pricing engine, invoicing, ledger (double-entry for A2A), payment (Mollie/Adyen/Stripe), payment routing, credits, dunning.

**Domain modules**:
- `src/rupiv/tax/` — EU VAT engine, VIES validation, OSS, ViDA, rate tables
- `src/rupiv/revenue_recognition/` — IFRS 15: obligations, allocation, schedules, variable consideration, journal entries
- `src/rupiv/entities/` — Multi-entity (BV, GmbH, SAS), hierarchy, intercompany billing
- `src/rupiv/policy/` — Declarative rules engine, approval workflows, thresholds
- `src/rupiv/pricing_studio/` — What-if simulation, A/B testing, revenue forecast, templates
- `src/rupiv/quoting/` — Quote builder, acceptance → subscription, contracts
- `src/rupiv/analytics/` — Payment costs, MRR/ARR, outcome metrics, cohorts, routing optimizer

**LangGraph agents**: `src/rupiv/agents/` — billing, dunning, compliance, outcome validation, quoting, revenue (IFRS 15), A2A settlement. Agents orchestrate domain modules.

**Workers**: `src/rupiv/workers/` — BullMQ consumers for async processing: event ingestion → ClickHouse, invoice generation, payment execution, revenue recalculation, VAT validation, simulations.

**Migrations**: `src/migrations/versions/` — Alembic with `script_location = src/migrations`.

**Python SDK**: `src/rupiv/sdk/python/rupiv/` — client, events, quotes, types.

### Frontend (React 19 + Vite + Tailwind v4)

`dashboard/src/` — Pages in `pages/`, shared components in `components/`. Uses React Router, TanStack React Query, Recharts, Lucide icons. API client in `lib/api.ts`.

### Infrastructure

Docker Compose services: `app` (FastAPI on :8000), `worker` (event processor), `postgres:16` (:5432), `redis:7` (:6379), `clickhouse` (:8123/:9000). ClickHouse initialized via `scripts/init_clickhouse.sql`.

## Testing

Tests use **in-memory SQLite** via `aiosqlite` — no external services required. `conftest.py` patches PG-specific types (JSONB → JSON, UUID → VARCHAR) for SQLite compatibility. The `app` fixture replaces lifespan with a no-op and overrides `get_db`/`get_settings` dependencies.

Key fixtures: `db_engine`, `db_session`, `app`, `client` (httpx AsyncClient via ASGITransport), `sample_customer`, `sample_plan`, `sample_event`, `make_event_payload()`.

`asyncio_mode = "auto"` in pytest config — no need to mark async tests individually.

## Coding Rules

1. **Type hints everywhere** — pyright strict mode is enforced
2. **Pydantic or dataclasses** for domain objects — never raw dicts
3. **Async for all I/O** — database, HTTP, Redis, ClickHouse
4. **`decimal.Decimal` for money** — never float. PG `NUMERIC(19,4)`, ClickHouse `Decimal64(4)`
5. **`structlog` with JSON output** — no `print()`
6. **Double-entry ledger** for A2A transactions — every tx has debit + credit
7. **Idempotency keys** on all payment/event endpoints
8. **EU VAT on every invoice** — reverse charge B2B, destination-based B2C
9. **IFRS 15** — every invoice triggers a revenue schedule
10. **Policy engine** — all state transitions pass through `src/rupiv/policy/engine.py`
11. **Ruff config**: line length 99, target Python 3.12, extensive lint rules including security (bandit), annotations, pytest style
12. **Multi-currency rounding** — round per line item, not totals

## Gotchas

- **ClickHouse is append-only** — no UPDATEs. Use ReplacingMergeTree for dedup.
- **Outcome validation is async** — don't bill on ingest, wait for agent confirmation.
- **SEPA settlement is T+1** — A2A ledger entries stay "pending" until Adyen confirms.
- **VIES API downtime** — cache validations 24h, queue retries.
- **Policy rule ordering** — priority order, first `reject` wins.
- **Render cold starts** — 30-50s. Health check at `/health` with 60s timeout.
- **Mollie webhooks are POST** — verify `X-Mollie-Signature` HMAC.

## Remaining Build Plan

Features still needed, ordered by priority. Phase 1 items are production blockers. All items verified by Ultraplan codebase audit (2026-04-09).

### Recently completed (this session)

- Customer self-service portal (JWT auth, invoices, usage, subscription) — `api/v1/portal.py`, `models/customer_user.py`
- Revenue leakage alerting (anomaly detection, alert rules, API, dashboard) — `analytics/anomaly.py`, `models/alert.py`, `api/v1/alerts.py`
- ERP/Accounting export (CSV, QuickBooks IIF, Xero with GL mapping) — `erp/formatters.py`, `api/v1/erp.py`
- Data transformation rules (engine, API, preview) — `transformations/engine.py`, `api/v1/transformations.py`
- Migrations 010-013, 58 new tests, 364/364 full suite green

### Phase 1: Production Blockers (~1 week, all independent)

**1. Payment Method Storage (HIGHEST URGENCY)**
`payment_worker.py` imports `PaymentMethod` from `billing/payment.py` which doesn't exist — worker crashes at startup. Additionally, `charge_invoice()` call signature on line 86 is wrong (passes `payment_method` but actual signature expects `MollieClient, Invoice, webhook_base_url`).
- Create `src/rupiv/models/payment_method.py` — table: `customer_id` FK, `provider` (mollie/stripe/adyen), `type` (card/ideal/sepa), `provider_method_id`, `is_default`, `last_four`, `expires_at`, `metadata_` JSONB
- Create `src/migrations/versions/014_payment_methods.py`
- Modify `src/rupiv/billing/payment.py` — add `PaymentMethod` frozen dataclass + new `charge_invoice_routed(session, invoice, payment_method, settings)` that dispatches to correct PSP client based on `payment_method.provider`
- Modify `src/rupiv/workers/payment_worker.py` — replace stub with DB lookup of customer's default method, fix call to use `charge_invoice_routed()`
- Test: `tests/test_payment_methods.py`

**2. Alert Worker**
Anomaly detection engine (`analytics/anomaly.py`) + models + API exist but no background worker runs checks.
- Create `src/rupiv/workers/alert_worker.py` — periodic (5min interval), loads active `AlertRule` rows, gathers metrics (MRR from `analytics/mrr_arr.py`, invoice counts from PG), calls `check_deviation()`, inserts `Alert` rows. Dedup: skip if open alert with same `alert_type + metric_name` exists within current period
- Follow worker pattern from `event_processor.py` (async loop, signal handlers, `_get_session_factory()` for DB)
- Entry point: `python -m rupiv.workers.alert_worker`

**3. Durable A2A Ledger**
`billing/ledger.py` uses in-memory `_entries` list (line 50) — all A2A transactions lost on restart. ORM model already exists in `models/ledger.py`.
- Rewrite `src/rupiv/billing/ledger.py` — each function creates its own session via `_get_session_factory()` (not passed in), because LangGraph agent nodes can't serialize DB sessions into state. Export a `LedgerEntryDTO` dataclass for API compatibility.
- Re-export `EntryType` and alias `LedgerStatus` as `EntryStatus` since `api/v1/a2a.py` imports `ledger.EntryType` and `ledger.LedgerEntry`
- Update `tests/test_ledger.py` — remove `_entries.clear()`, add `db_session` fixture
- No migration needed — `ledger_entries` table already exists

**4. VAT Worker Persistence**
VIES validation runs (`vat_worker.py:46`) but result never saved to customer record (TODO at line 57).
- Add `vat_valid: Mapped[bool | None]` and `vat_validated_at: Mapped[datetime | None]` to `src/rupiv/models/customer.py`
- Create `src/migrations/versions/015_customer_vat_validation.py`
- Modify `src/rupiv/workers/vat_worker.py` — after validation, open session via `_get_session_factory()`, `UPDATE customers SET vat_valid, vat_validated_at WHERE id = customer_id`

**5. Tracing + Audit Middleware Registration**
Both middlewares exist in `src/rupiv/api/middleware/` but are never added to the app in `main.py`.
- Modify `src/rupiv/main.py` — after CORS middleware, add `AuditMiddleware` (inner) then `TracingMiddleware` (outer, so trace IDs available for audit). Starlette order: last added = outermost.

### Phase 2: High-Value Features (~1-2 weeks)

**6. Outbound Webhooks**
Customers need notifications for `invoice.created`, `invoice.paid`, `payment.failed`, `subscription.canceled`.
- Create `src/rupiv/models/webhook_endpoint.py` — `WebhookEndpoint`: `customer_id`, `url`, `secret` (auto-generated HMAC key), `events` (JSONB array of subscribed types), `is_active`, `failure_count`
- Create `src/rupiv/models/webhook_delivery.py` — `WebhookDelivery`: `endpoint_id`, `event_type`, `payload` JSONB, `response_status`, `attempt`, `delivered_at`
- Create `src/rupiv/webhooks/dispatcher.py` — `dispatch_event(event_type, payload)` pushes to Redis list `rupiv:webhooks:outbound`
- Create `src/rupiv/workers/webhook_worker.py` — BLPOP worker, query matching endpoints, POST with HMAC-SHA256 in `X-Rupiv-Signature` header, 3 retries (2s/4s/8s backoff), circuit breaker: skip endpoint if `failure_count >= 10`
- Create `src/rupiv/api/v1/webhook_endpoints.py` — CRUD + `GET /{id}/deliveries`
- Create `src/migrations/versions/016_webhook_endpoints.py`
- Wire dispatch: `workers/invoice_worker.py` (after invoice creation), `billing/payment.py` (after `process_webhook` / `process_stripe_webhook` status update)

**7. PDF Invoice Generation**
- Add `weasyprint` + `jinja2` to `pyproject.toml`
- Create `src/rupiv/invoicing/pdf.py` — `generate_invoice_pdf(invoice) -> bytes` with Jinja2 HTML template + weasyprint
- Create `src/rupiv/invoicing/templates/invoice.html` — company header, line items table, VAT breakdown, totals, reverse charge notation if `tax_type == "reverse_charge"`
- Add `GET /v1/invoices/{id}/pdf` and `GET /v1/portal/invoices/{id}/pdf` endpoints returning `StreamingResponse`
- Generate on-demand, cache in Redis with 1h TTL

**8. ECB Daily Rates**
`src/rupiv/entities/currency.py` `fetch_rates()` (line 107) returns hardcoded `_MVP_RATES` with comment showing where HTTP call goes.
- Replace body with `httpx.AsyncClient` call to `https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A?lastNObservations=1&format=csvdata`
- Add `_parse_ecb_csv(text) -> dict[str, Decimal]` helper
- Keep `_MVP_RATES` as fallback (ECB is occasionally down). Existing 24h cache TTL is appropriate.
- `httpx` is already a dependency

### Phase 3: Polish (defer)

**9. Audit Log for Reads**
- Add `AUDIT_READS: bool = Field(default=False)` to `src/rupiv/config.py`
- Modify `src/rupiv/api/middleware/audit.py` — when enabled, log GETs only on sensitive paths (`/customers/{id}`, `/invoices/{id}`, `/payment-methods`). Use same fire-and-forget `asyncio.create_task` pattern already in place.
- Depends on Phase 1 item 5 (middleware must be registered first)

### Migration Sequence

| # | Name | Revises |
|---|------|---------|
| 014 | `payment_methods` | 013_transformation_rules |
| 015 | `customer_vat_validation` | 014_payment_methods |
| 016 | `webhook_endpoints` + `webhook_deliveries` | 015_customer_vat_validation |
