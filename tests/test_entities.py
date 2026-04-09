"""Tests for the multi-entity and multi-currency module."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.entities.currency import ECBRateProvider, round_currency
from rupiv.entities.entity import (
    Jurisdiction,
    create_entity,
    get_entity_with_children,
    validate_entity_type_for_country,
)
from rupiv.entities.hierarchy import EntityTree
from rupiv.models.entity import EntityType

# ---------------------------------------------------------------------------
# Entity creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_entity(db_session: AsyncSession) -> None:
    """Create a BV entity in the Netherlands."""
    entity = await create_entity(
        db_session,
        name="Acme BV",
        entity_type=EntityType.BV,
        country_code="NL",
        currency="EUR",
        vat_number="NL123456789B01",
    )
    await db_session.commit()

    assert entity.id is not None
    assert entity.name == "Acme BV"
    assert entity.entity_type == EntityType.BV
    assert entity.country_code == "NL"
    assert entity.default_currency == "EUR"
    assert entity.vat_number == "NL123456789B01"
    assert entity.is_active is True
    assert entity.parent_id is None


@pytest.mark.asyncio
async def test_create_child_entity(db_session: AsyncSession) -> None:
    """Create a GmbH entity as a child of a BV parent."""
    parent = await create_entity(
        db_session,
        name="Holding BV",
        entity_type=EntityType.BV,
        country_code="NL",
        currency="EUR",
    )
    await db_session.flush()

    child = await create_entity(
        db_session,
        name="Tochter GmbH",
        entity_type=EntityType.GMBH,
        country_code="DE",
        currency="EUR",
        parent_id=parent.id,
        vat_number="DE123456789",
    )
    await db_session.commit()

    assert child.parent_id == parent.id
    assert child.entity_type == EntityType.GMBH
    assert child.country_code == "DE"

    # Verify parent has child via eager load
    loaded = await get_entity_with_children(db_session, parent.id)
    assert loaded is not None
    assert len(loaded.children) == 1
    assert loaded.children[0].id == child.id


# ---------------------------------------------------------------------------
# Entity type validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_entity_type_valid() -> None:
    """BV is valid for NL, GmbH for DE."""
    assert validate_entity_type_for_country(EntityType.BV, "NL") is True
    assert validate_entity_type_for_country(EntityType.GMBH, "DE") is True
    assert validate_entity_type_for_country(EntityType.SAS, "FR") is True
    assert validate_entity_type_for_country(EntityType.LTD, "GB") is True
    assert validate_entity_type_for_country(EntityType.LTD, "IE") is True
    assert validate_entity_type_for_country(EntityType.SRL, "IT") is True
    assert validate_entity_type_for_country(EntityType.AB, "SE") is True
    assert validate_entity_type_for_country(EntityType.OY, "FI") is True


@pytest.mark.asyncio
async def test_validate_entity_type_invalid() -> None:
    """BV is not valid for DE, GmbH is not valid for NL."""
    assert validate_entity_type_for_country(EntityType.BV, "DE") is False
    assert validate_entity_type_for_country(EntityType.GMBH, "NL") is False
    assert validate_entity_type_for_country(EntityType.SAS, "DE") is False


@pytest.mark.asyncio
async def test_validate_entity_type_other_always_valid() -> None:
    """OTHER entity type is valid for any country."""
    assert validate_entity_type_for_country(EntityType.OTHER, "NL") is True
    assert validate_entity_type_for_country(EntityType.OTHER, "US") is True
    assert validate_entity_type_for_country(EntityType.OTHER, "JP") is True


@pytest.mark.asyncio
async def test_create_entity_invalid_type_raises(
    db_session: AsyncSession,
) -> None:
    """Creating a BV in DE should raise ValueError."""
    with pytest.raises(ValueError, match="not valid"):
        await create_entity(
            db_session,
            name="Bad Entity",
            entity_type=EntityType.BV,
            country_code="DE",
            currency="EUR",
        )


# ---------------------------------------------------------------------------
# Entity hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entity_hierarchy(db_session: AsyncSession) -> None:
    """Test ancestors, descendants, root, and siblings traversal."""
    # Build a tree: root -> child_a, child_b -> grandchild
    root = await create_entity(
        db_session,
        name="Root BV",
        entity_type=EntityType.BV,
        country_code="NL",
        currency="EUR",
    )
    await db_session.flush()

    child_a = await create_entity(
        db_session,
        name="Child A GmbH",
        entity_type=EntityType.GMBH,
        country_code="DE",
        currency="EUR",
        parent_id=root.id,
    )
    await db_session.flush()

    child_b = await create_entity(
        db_session,
        name="Child B SAS",
        entity_type=EntityType.SAS,
        country_code="FR",
        currency="EUR",
        parent_id=root.id,
    )
    await db_session.flush()

    grandchild = await create_entity(
        db_session,
        name="Grandchild Ltd",
        entity_type=EntityType.LTD,
        country_code="GB",
        currency="GBP",
        parent_id=child_a.id,
    )
    await db_session.commit()

    tree = EntityTree()

    # Ancestors of grandchild: [child_a, root]
    ancestors = await tree.get_ancestors(db_session, grandchild.id)
    ancestor_ids = [a.id for a in ancestors]
    assert child_a.id in ancestor_ids
    assert root.id in ancestor_ids
    assert len(ancestors) == 2

    # Descendants of root: [child_a, child_b, grandchild]
    descendants = await tree.get_descendants(db_session, root.id)
    descendant_ids = {d.id for d in descendants}
    assert child_a.id in descendant_ids
    assert child_b.id in descendant_ids
    assert grandchild.id in descendant_ids
    assert len(descendants) == 3

    # Root of grandchild
    found_root = await tree.get_root(db_session, grandchild.id)
    assert found_root is not None
    assert found_root.id == root.id

    # Root of root is itself
    found_root2 = await tree.get_root(db_session, root.id)
    assert found_root2 is not None
    assert found_root2.id == root.id

    # Siblings of child_a: [child_b]
    siblings = await tree.get_siblings(db_session, child_a.id)
    assert len(siblings) == 1
    assert siblings[0].id == child_b.id


# ---------------------------------------------------------------------------
# Move entity (reparent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_entity(db_session: AsyncSession) -> None:
    """Reparent an entity to a new parent."""
    root = await create_entity(
        db_session,
        name="MoveRoot BV",
        entity_type=EntityType.BV,
        country_code="NL",
        currency="EUR",
    )
    await db_session.flush()

    parent_a = await create_entity(
        db_session,
        name="Parent A GmbH",
        entity_type=EntityType.GMBH,
        country_code="DE",
        currency="EUR",
        parent_id=root.id,
    )
    await db_session.flush()

    parent_b = await create_entity(
        db_session,
        name="Parent B SAS",
        entity_type=EntityType.SAS,
        country_code="FR",
        currency="EUR",
        parent_id=root.id,
    )
    await db_session.flush()

    child = await create_entity(
        db_session,
        name="Moveable Ltd",
        entity_type=EntityType.LTD,
        country_code="GB",
        currency="GBP",
        parent_id=parent_a.id,
    )
    await db_session.commit()

    tree = EntityTree()

    # Move child from parent_a to parent_b
    moved = await tree.move_entity(db_session, child.id, parent_b.id)
    await db_session.commit()

    assert moved.parent_id == parent_b.id

    # Verify child is now under parent_b
    descendants_b = await tree.get_descendants(db_session, parent_b.id)
    assert any(d.id == child.id for d in descendants_b)

    # Verify child is no longer under parent_a
    descendants_a = await tree.get_descendants(db_session, parent_a.id)
    assert not any(d.id == child.id for d in descendants_a)


@pytest.mark.asyncio
async def test_move_entity_cycle_prevention(
    db_session: AsyncSession,
) -> None:
    """Moving a parent under its own child should raise ValueError."""
    root = await create_entity(
        db_session,
        name="CycleRoot BV",
        entity_type=EntityType.BV,
        country_code="NL",
        currency="EUR",
    )
    await db_session.flush()

    child = await create_entity(
        db_session,
        name="CycleChild GmbH",
        entity_type=EntityType.GMBH,
        country_code="DE",
        currency="EUR",
        parent_id=root.id,
    )
    await db_session.commit()

    tree = EntityTree()
    with pytest.raises(ValueError, match="cycle"):
        await tree.move_entity(db_session, root.id, child.id)


# ---------------------------------------------------------------------------
# Currency conversion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_currency_conversion() -> None:
    """Convert EUR to USD and back."""
    provider = ECBRateProvider()

    # EUR -> USD
    usd_amount = await provider.convert(
        Decimal("100.00"),
        "EUR",
        "USD",
    )
    assert usd_amount > Decimal("100.00")  # USD rate > 1
    assert isinstance(usd_amount, Decimal)

    # USD -> EUR
    eur_amount = await provider.convert(usd_amount, "USD", "EUR")
    assert isinstance(eur_amount, Decimal)
    # Should be close to 100.00 (within rounding tolerance)
    assert abs(eur_amount - Decimal("100.00")) < Decimal("0.02")


@pytest.mark.asyncio
async def test_currency_round_trip() -> None:
    """Convert EUR -> GBP -> EUR and verify minimal loss from rounding."""
    provider = ECBRateProvider()

    original = Decimal("1000.00")
    gbp = await provider.convert(original, "EUR", "GBP")
    back_to_eur = await provider.convert(gbp, "GBP", "EUR")

    # Round-trip loss should be less than 0.02 EUR (rounding artefact)
    loss = abs(back_to_eur - original)
    assert loss < Decimal("0.02"), f"Round-trip loss too high: {loss}"


@pytest.mark.asyncio
async def test_currency_same_currency() -> None:
    """Converting same currency returns the same amount."""
    provider = ECBRateProvider()
    result = await provider.convert(Decimal("42.50"), "EUR", "EUR")
    assert result == Decimal("42.50")


@pytest.mark.asyncio
async def test_ecb_rate_cache() -> None:
    """Second call uses the in-memory cache."""
    provider = ECBRateProvider()

    # First call populates cache
    rate1 = await provider.get_rate("EUR", "USD")
    ts1 = provider._cache_timestamp

    # Second call should use cache (timestamp unchanged)
    rate2 = await provider.get_rate("EUR", "USD")
    ts2 = provider._cache_timestamp

    assert rate1 == rate2
    assert ts1 == ts2  # Cache was not refreshed


@pytest.mark.asyncio
async def test_currency_unsupported_raises() -> None:
    """Unsupported currency should raise ValueError."""
    provider = ECBRateProvider()
    with pytest.raises(ValueError, match="Unsupported currency"):
        await provider.get_rate("EUR", "XYZ")


# ---------------------------------------------------------------------------
# Currency rounding
# ---------------------------------------------------------------------------


def test_round_currency_standard() -> None:
    """Standard currencies round to 2 decimal places."""
    assert round_currency(Decimal("10.555"), "EUR") == Decimal("10.56")
    assert round_currency(Decimal("10.554"), "USD") == Decimal("10.55")


def test_round_currency_zero_decimal() -> None:
    """JPY and KRW round to 0 decimal places."""
    assert round_currency(Decimal("1234.5"), "JPY") == Decimal("1235")
    assert round_currency(Decimal("1234.4"), "KRW") == Decimal("1234")


# ---------------------------------------------------------------------------
# Jurisdiction mapping
# ---------------------------------------------------------------------------


def test_jurisdiction_countries_for_type() -> None:
    """Verify jurisdiction mappings."""
    assert "NL" in Jurisdiction.countries_for_type(EntityType.BV)
    assert "DE" in Jurisdiction.countries_for_type(EntityType.GMBH)
    assert "AT" in Jurisdiction.countries_for_type(EntityType.GMBH)


def test_jurisdiction_types_for_country() -> None:
    """Verify reverse jurisdiction lookup."""
    nl_types = Jurisdiction.types_for_country("NL")
    assert EntityType.BV in nl_types
    assert EntityType.OTHER in nl_types  # OTHER always included
