"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Rupiv.ai application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://rupiv:rupiv@localhost:5432/rupiv",
        description="PostgreSQL async connection URL",
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    CLICKHOUSE_URL: str = Field(
        default="http://localhost:8123",
        description="ClickHouse HTTP interface URL",
    )
    CLICKHOUSE_DATABASE: str = Field(
        default="rupiv",
        description="ClickHouse database name",
    )

    # --- Payment providers ---
    MOLLIE_API_KEY: str | None = Field(
        default=None,
        description="Mollie API key (optional in dev)",
    )
    ADYEN_API_KEY: str | None = Field(
        default=None,
        description="Adyen API key (optional in dev)",
    )
    ADYEN_MERCHANT_ACCOUNT: str | None = Field(
        default=None,
        description="Adyen merchant account identifier (optional in dev)",
    )

    # --- Auth ---
    CLERK_SECRET_KEY: str | None = Field(
        default=None,
        description="Clerk secret key for JWT verification (optional in dev)",
    )

    # --- Application ---
    APP_ENV: str = Field(
        default="development",
        description="Application environment: development | staging | production",
    )
    APP_SECRET_KEY: str = Field(
        default="change-me-in-production",
        description="Secret key for signing tokens and cookies",
    )
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:5173"],
        description="Allowed CORS origins",
    )

    # --- Observability ---
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(
        default=None,
        description="OpenTelemetry OTLP exporter endpoint",
    )


def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
