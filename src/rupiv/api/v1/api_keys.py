"""API key management endpoints — CRUD for customer API keys."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.api.middleware.auth import generate_api_key, get_current_customer
from rupiv.db import get_db
from rupiv.models.api_key import ApiKey
from rupiv.models.customer import Customer

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ApiKeyCreate(BaseModel):
    """Request body for creating a new API key."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label")
    prefix: str = Field(
        default="rp_live_",
        pattern=r"^rp_(live|test)_$",
        description="Key prefix: rp_live_ or rp_test_",
    )
    scopes: list[str] | None = Field(
        default=None,
        description="Allowed scopes; null means all scopes",
    )


class ApiKeyCreatedResponse(BaseModel):
    """Returned once when a key is created — includes the full key."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    key: str = Field(description="Full API key — shown only once, store it securely")
    scopes: list[str] | None
    created_at: str


class ApiKeyListItem(BaseModel):
    """An API key summary (never exposes the full key)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    key_hint: str = Field(description="Prefix + last 4 characters for identification")
    is_active: bool
    scopes: list[str] | None
    created_at: str
    last_used_at: str | None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
)
async def create_api_key(
    payload: ApiKeyCreate,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedResponse:
    """Generate a new API key for the authenticated customer.

    The full key is returned **only in this response**.  It cannot be
    retrieved again — only a masked hint is available via the list endpoint.
    """
    full_key, key_hash = generate_api_key(prefix=payload.prefix)

    api_key = ApiKey(
        customer_id=customer.id,
        key_prefix=payload.prefix,
        key_hash=key_hash,
        name=payload.name,
        is_active=True,
        scopes=payload.scopes,
    )
    session.add(api_key)
    await session.flush()

    logger.info(
        "api_key_created",
        api_key_id=str(api_key.id),
        customer_id=str(customer.id),
        name=payload.name,
        prefix=payload.prefix,
    )

    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        key=full_key,
        scopes=api_key.scopes,
        created_at=api_key.created_at.isoformat(),
    )


@router.get(
    "",
    response_model=list[ApiKeyListItem],
    summary="List API keys for the current customer",
)
async def list_api_keys(
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> list[ApiKeyListItem]:
    """Return all API keys for the authenticated customer.

    The full key is never returned — only the prefix and last 4 characters
    of the hash are shown for identification.
    """
    stmt = (
        select(ApiKey).where(ApiKey.customer_id == customer.id).order_by(ApiKey.created_at.desc())
    )
    result = await session.execute(stmt)
    keys = result.scalars().all()

    items: list[ApiKeyListItem] = []
    for k in keys:
        items.append(
            ApiKeyListItem(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                key_hint=f"{k.key_prefix}...{k.key_hash[-4:]}",
                is_active=k.is_active,
                scopes=k.scopes,
                created_at=k.created_at.isoformat(),
                last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            ),
        )
    return items


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an API key",
)
async def deactivate_api_key(
    key_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Deactivate (soft-delete) an API key.

    The key remains in the database for audit purposes but will no longer
    pass authentication.
    """
    stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.customer_id == customer.id)
    result = await session.execute(stmt)
    api_key: ApiKey | None = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    if not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API key is already deactivated",
        )

    await session.execute(update(ApiKey).where(ApiKey.id == key_id).values(is_active=False))

    logger.info(
        "api_key_deactivated",
        api_key_id=str(key_id),
        customer_id=str(customer.id),
    )
