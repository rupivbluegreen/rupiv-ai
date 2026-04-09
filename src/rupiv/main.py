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

    # Redis connection
    from redis.asyncio import Redis

    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    app.state.redis = redis_client
    log.info("redis_connected", url=settings.REDIS_URL)

    # ClickHouse client
    import clickhouse_connect

    ch_client = clickhouse_connect.get_client(
        host=settings.CLICKHOUSE_URL.replace("http://", "").split(":")[0],
        port=int(settings.CLICKHOUSE_URL.split(":")[-1]),
        database=settings.CLICKHOUSE_DATABASE,
    )
    app.state.clickhouse = ch_client
    log.info("clickhouse_connected", database=settings.CLICKHOUSE_DATABASE)

    yield

    # --- Shutdown ---
    log.info("shutting_down_app")
    await engine.dispose()
    await redis_client.aclose()
    ch_client.close()
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    _configure_logging()

    settings = get_settings()

    app = FastAPI(
        title="Rupiv.ai API",
        version=__version__,
        lifespan=_lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include v1 API router
    app.include_router(v1_router)

    # Health check
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app: FastAPI = create_app()
