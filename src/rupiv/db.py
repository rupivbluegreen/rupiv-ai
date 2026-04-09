"""Database setup — async engine, session factory, and base model."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from rupiv.config import get_settings

# ---------------------------------------------------------------------------
# Naming convention for constraints (keeps Alembic migrations deterministic)
# ---------------------------------------------------------------------------
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


def _get_engine() -> AsyncEngine:
    """Lazily create the async engine from settings."""
    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.APP_ENV == "development",
        pool_size=5,
        max_overflow=10,
    )


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Lazily create the session factory."""
    return async_sessionmaker(
        _get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, rolling back on error."""
    async with _get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Base declarative model
# ---------------------------------------------------------------------------
class Base(AsyncAttrs, DeclarativeBase):
    """Base model with common columns shared by every table."""

    metadata = metadata

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
