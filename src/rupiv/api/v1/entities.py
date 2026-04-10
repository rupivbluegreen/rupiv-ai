"""Legal entity CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.api.middleware.auth import get_current_api_key
from rupiv.db import get_db
from rupiv.entities.entity import create_entity
from rupiv.models.api_key import ApiKey
from rupiv.entities.hierarchy import EntityTree
from rupiv.models.entity import EntityType, LegalEntity

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/entities", tags=["entities"])


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class EntityTypeEnum(str, Enum):
    """Supported legal entity types."""

    BV = "bv"
    GMBH = "gmbh"
    SAS = "sas"
    LTD = "ltd"
    SRL = "srl"
    AB = "ab"
    OY = "oy"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class EntityCreate(BaseModel):
    """Request body for creating a legal entity."""

    name: str
    entity_type: EntityTypeEnum
    country_code: str = Field(max_length=2, description="ISO 3166-1 alpha-2")
    currency: str = Field(default="EUR", max_length=3, description="ISO 4217")
    parent_id: uuid.UUID | None = None
    vat_number: str | None = None


class EntityUpdate(BaseModel):
    """Request body for updating a legal entity."""

    name: str | None = None
    entity_type: EntityTypeEnum | None = None
    country_code: str | None = None
    currency: str | None = None
    parent_id: uuid.UUID | None = None
    vat_number: str | None = None
    is_active: bool | None = None


class EntityResponse(BaseModel):
    """Legal entity resource representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    entity_type: EntityTypeEnum
    country_code: str
    default_currency: str
    parent_id: uuid.UUID | None = None
    vat_number: str | None = None
    registration_number: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EntityListResponse(BaseModel):
    """Paginated list of legal entities."""

    items: list[EntityResponse]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=EntityListResponse, summary="List entities")
async def list_entities(
    parent_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> EntityListResponse:
    """Return a paginated list of legal entities, optionally filtered by parent."""
    logger.info(
        "list_entities",
        parent_id=str(parent_id) if parent_id else None,
        limit=limit,
        offset=offset,
    )

    count_stmt = select(func.count(LegalEntity.id))
    query_stmt = (
        select(LegalEntity).order_by(LegalEntity.created_at.desc()).limit(limit).offset(offset)
    )

    if parent_id is not None:
        count_stmt = count_stmt.where(LegalEntity.parent_id == parent_id)
        query_stmt = query_stmt.where(LegalEntity.parent_id == parent_id)

    total: int = (await session.execute(count_stmt)).scalar_one()

    result = await session.execute(query_stmt)
    rows: list[LegalEntity] = list(result.scalars().all())

    return EntityListResponse(
        items=[EntityResponse.model_validate(row) for row in rows],
        total=total,
    )


@router.post(
    "",
    response_model=EntityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a legal entity",
)
async def create_entity_endpoint(
    payload: EntityCreate,
    session: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> EntityResponse:
    """Create a new legal entity."""
    logger.info("create_entity", name=payload.name, entity_type=payload.entity_type.value)

    try:
        entity = await create_entity(
            session,
            name=payload.name,
            entity_type=EntityType(payload.entity_type.value),
            country_code=payload.country_code,
            currency=payload.currency,
            parent_id=payload.parent_id,
            vat_number=payload.vat_number,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await session.refresh(entity)
    return EntityResponse.model_validate(entity)


@router.get("/{entity_id}", response_model=EntityResponse, summary="Get a legal entity")
async def get_entity(
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> EntityResponse:
    """Return a single legal entity by ID."""
    logger.info("get_entity", entity_id=str(entity_id))

    result = await session.execute(select(LegalEntity).where(LegalEntity.id == entity_id))
    entity: LegalEntity | None = result.scalar_one_or_none()

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity {entity_id} not found",
        )

    return EntityResponse.model_validate(entity)


@router.patch("/{entity_id}", response_model=EntityResponse, summary="Update a legal entity")
async def update_entity(
    entity_id: uuid.UUID,
    payload: EntityUpdate,
    session: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> EntityResponse:
    """Partially update a legal entity."""
    logger.info("update_entity", entity_id=str(entity_id))

    result = await session.execute(select(LegalEntity).where(LegalEntity.id == entity_id))
    entity: LegalEntity | None = result.scalar_one_or_none()

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity {entity_id} not found",
        )

    # Map Pydantic field names to ORM attribute names
    field_mapping: dict[str, str] = {
        "currency": "default_currency",
    }

    update_data: dict[str, object] = payload.model_dump(exclude_unset=True)

    # Convert entity_type enum if present
    if "entity_type" in update_data and update_data["entity_type"] is not None:
        update_data["entity_type"] = EntityType(update_data["entity_type"].value)  # type: ignore[union-attr]

    for field_name, value in update_data.items():
        attr_name: str = field_mapping.get(field_name, field_name)
        setattr(entity, attr_name, value)

    await session.flush()
    await session.refresh(entity)

    return EntityResponse.model_validate(entity)


@router.get(
    "/{entity_id}/children",
    response_model=EntityListResponse,
    summary="Get child entities",
)
async def get_entity_children(
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> EntityListResponse:
    """Return all direct children of a legal entity."""
    logger.info("get_entity_children", entity_id=str(entity_id))

    # Verify entity exists
    result = await session.execute(select(LegalEntity).where(LegalEntity.id == entity_id))
    entity: LegalEntity | None = result.scalar_one_or_none()

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity {entity_id} not found",
        )

    # Fetch children
    result = await session.execute(
        select(LegalEntity)
        .where(LegalEntity.parent_id == entity_id)
        .order_by(LegalEntity.created_at.desc()),
    )
    children: list[LegalEntity] = list(result.scalars().all())

    return EntityListResponse(
        items=[EntityResponse.model_validate(child) for child in children],
        total=len(children),
    )


@router.get(
    "/{entity_id}/ancestors",
    response_model=EntityListResponse,
    summary="Get ancestor chain to root",
)
async def get_entity_ancestors(
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> EntityListResponse:
    """Return the ancestor chain from entity to root (bottom-up)."""
    logger.info("get_entity_ancestors", entity_id=str(entity_id))

    # Verify entity exists
    result = await session.execute(select(LegalEntity).where(LegalEntity.id == entity_id))
    entity: LegalEntity | None = result.scalar_one_or_none()

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity {entity_id} not found",
        )

    ancestors: list[LegalEntity] = await EntityTree.get_ancestors(session, entity_id)

    return EntityListResponse(
        items=[EntityResponse.model_validate(a) for a in ancestors],
        total=len(ancestors),
    )
