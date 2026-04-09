"""Entity business logic — creation, validation, and jurisdiction mapping."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.entity import EntityType, LegalEntity

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Jurisdiction mapping: entity type → valid country codes
# ---------------------------------------------------------------------------

class Jurisdiction:
    """Maps entity types to the country codes where they are valid."""

    _MAPPING: dict[EntityType, set[str]] = {
        EntityType.BV: {"NL"},
        EntityType.GMBH: {"DE", "AT", "CH"},
        EntityType.SAS: {"FR"},
        EntityType.LTD: {"GB", "IE"},
        EntityType.SRL: {"IT", "RO"},
        EntityType.AB: {"SE"},
        EntityType.OY: {"FI"},
        EntityType.OTHER: set(),  # OTHER is valid anywhere
    }

    @classmethod
    def countries_for_type(cls, entity_type: EntityType) -> set[str]:
        """Return country codes where the given entity type is valid."""
        return cls._MAPPING.get(entity_type, set())

    @classmethod
    def types_for_country(cls, country_code: str) -> list[EntityType]:
        """Return entity types valid in the given country."""
        result: list[EntityType] = []
        for etype, countries in cls._MAPPING.items():
            if country_code.upper() in countries:
                result.append(etype)
        # OTHER is always valid
        if EntityType.OTHER not in result:
            result.append(EntityType.OTHER)
        return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_entity_type_for_country(
    entity_type: EntityType,
    country_code: str,
) -> bool:
    """Check whether an entity type is valid for a given country.

    ``OTHER`` is accepted for any country.  For named types, the country
    must appear in the jurisdiction mapping.
    """
    if entity_type == EntityType.OTHER:
        return True
    valid_countries = Jurisdiction.countries_for_type(entity_type)
    return country_code.upper() in valid_countries


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


async def create_entity(
    session: AsyncSession,
    *,
    name: str,
    entity_type: EntityType,
    country_code: str,
    currency: str = "EUR",
    parent_id: uuid.UUID | None = None,
    vat_number: str | None = None,
    registration_number: str | None = None,
    metadata_: dict[str, Any] | None = None,
) -> LegalEntity:
    """Create a new legal entity, validating type/country compatibility."""
    country_code = country_code.upper()

    if not validate_entity_type_for_country(entity_type, country_code):
        msg = (
            f"Entity type {entity_type.value} is not valid "
            f"for country {country_code}"
        )
        raise ValueError(msg)

    entity = LegalEntity(
        name=name,
        entity_type=entity_type,
        country_code=country_code,
        default_currency=currency.upper(),
        parent_id=parent_id,
        vat_number=vat_number,
        registration_number=registration_number,
        metadata_=metadata_,
    )
    session.add(entity)
    await session.flush()

    logger.info(
        "entity_created",
        entity_id=str(entity.id),
        name=name,
        entity_type=entity_type.value,
        country_code=country_code,
        parent_id=str(parent_id) if parent_id else None,
    )
    return entity


async def get_entity_with_children(
    session: AsyncSession,
    entity_id: uuid.UUID,
) -> LegalEntity | None:
    """Fetch an entity with its children eagerly loaded."""
    stmt = (
        select(LegalEntity)
        .where(LegalEntity.id == entity_id)
        .options(selectinload(LegalEntity.children))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
