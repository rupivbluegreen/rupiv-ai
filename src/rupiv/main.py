"""FastAPI application factory for Rupiv.ai."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rupiv import __version__
from rupiv.api.v1 import v1_router
from rupiv.config import Settings, get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


def _configure_logging() -> None:
    """Configure structlog for JSON output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown of external connections."""
    settings: Settings = get_settings()
    log = logger.bind(app_env=settings.APP_ENV)

    # --- Startup ---
    log.info("starting_app", version=__version__)

    # Database pool (SQLAlchemy async engine)
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    app.state.db_engine = engine
    log.info("database_connected", url=settings.DATABASE_URL.split("@")[-1])

    # Redis connection (optional in development — app continues without it)
    redis_client = None
    try:
        from redis.asyncio import Redis

        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis_client.ping()
        log.info("redis_connected", url=settings.REDIS_URL)
    except Exception:
        log.warning(
            "redis_unavailable",
            url=settings.REDIS_URL,
            hint="App will continue without Redis. Caching and queues disabled.",
        )
        redis_client = None
    app.state.redis = redis_client

    # ClickHouse client (optional — app continues without it)
    ch_client = None
    try:
        import clickhouse_connect

        ch_client = clickhouse_connect.get_client(
            host=settings.CLICKHOUSE_URL.replace("http://", "").split(":")[0],
            port=int(settings.CLICKHOUSE_URL.split(":")[-1]),
            database=settings.CLICKHOUSE_DATABASE,
        )
        # Verify connectivity
        ch_client.query("SELECT 1")
        log.info("clickhouse_connected", database=settings.CLICKHOUSE_DATABASE)
    except Exception:
        log.warning(
            "clickhouse_unavailable",
            url=settings.CLICKHOUSE_URL,
            hint="App will continue without ClickHouse. Analytics disabled.",
        )
        ch_client = None
    app.state.clickhouse = ch_client

    yield

    # --- Shutdown ---
    log.info("shutting_down_app")
    await engine.dispose()
    if redis_client is not None:
        await redis_client.aclose()
    if ch_client is not None:
        ch_client.close()
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    _configure_logging()

    settings = get_settings()

    app = FastAPI(
        title="Rupiv.ai API",
        description=(
            "Outcome-based billing infrastructure for AI companies selling into Europe. "
            "Ingest usage and outcome events, manage customers, plans, subscriptions, "
            "invoices, quotes, credits, and revenue recognition — with EU VAT, IFRS 15, "
            "and GDPR compliance built in. Supports agent-to-agent (A2A) autonomous "
            "payments over SEPA fiat rails."
        ),
        version=__version__,
        lifespan=_lifespan,
        openapi_tags=[
            {
                "name": "events",
                "description": "Ingest usage and outcome events for metering and billing.",
            },
            {
                "name": "customers",
                "description": "Create, read, update, and list customer records.",
            },
            {
                "name": "entities",
                "description": "Manage legal entities (BV, GmbH, SAS) and their hierarchy.",
            },
            {
                "name": "plans",
                "description": "Define billing plans with flat, usage, outcome, hybrid, tiered, or credit pricing rules.",
            },
            {
                "name": "subscriptions",
                "description": "Assign customers to plans and manage subscription lifecycle.",
            },
            {
                "name": "quotes",
                "description": "Generate, send, and accept pricing quotes (quote-to-cash).",
            },
            {
                "name": "invoices",
                "description": "View and manage invoices with EU VAT line items.",
            },
            {
                "name": "revenue",
                "description": "IFRS 15 revenue recognition schedules and journal entries.",
            },
            {
                "name": "credits",
                "description": "Pre-purchased credit balances and consumption tracking.",
            },
            {
                "name": "analytics",
                "description": "Payment cost analytics, MRR/ARR metrics, and routing optimisation.",
            },
            {
                "name": "simulate",
                "description": "Pricing Studio — what-if simulations, revenue forecasting, and pricing templates.",
            },
            {
                "name": "a2a",
                "description": "Agent-to-agent autonomous payments via SEPA credit transfer.",
            },
            {
                "name": "webhooks",
                "description": "Receive payment-provider callbacks from Mollie and Adyen.",
            },
            {
                "name": "api-keys",
                "description": "Manage API keys for SDK and programmatic access.",
            },
            {
                "name": "onboarding",
                "description": "Self-serve signup, billing setup, and account activation.",
            },
            {
                "name": "compliance",
                "description": "GDPR, DORA, and EU VAT compliance checks.",
            },
            {
                "name": "stream",
                "description": "Real-time WebSocket stream of billing events.",
            },
        ],
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware stack (Starlette: last added = outermost)
    from rupiv.api.middleware.audit import AuditMiddleware
    from rupiv.api.middleware.tracing import TracingMiddleware

    app.add_middleware(AuditMiddleware)   # innermost — logs after processing
    app.add_middleware(TracingMiddleware)  # outermost — trace IDs for all
    # Note: rate limiting is applied per-endpoint via FastAPI Depends()
    # (see rupiv.api.middleware.rate_limit.rate_limit_default / rate_limit_events)

    # Include v1 API router
    app.include_router(v1_router)

    # Health check
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app: FastAPI = create_app()
