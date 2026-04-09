"""Entity tree management — ancestors, descendants, reparenting."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.entity import LegalEntity

logger = structlog.get_logger(__name__)


class EntityTree:
    """Operations on the legal-entity hierarchy.

    All methods are async and accept an ``AsyncSession``.  The hierarchy
    is stored as an adjacency list (``parent_id`` FK) and traversed
    iteratively to avoid CTE compatibility issues with SQLite in tests.
    """

    @staticmethod
    async def get_ancestors(
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> list[LegalEntity]:
        """Walk up from *entity_id* to the root, returning ancestors bottom-up.

        The entity itself is **not** included in the result.
        """
        ancestors: list[LegalEntity] = []
        current_id: uuid.UUID | None = entity_id

        # Load the starting entity to get its parent_id
        stmt = select(LegalEntity).where(LegalEntity.id == current_id)
        result = await session.execute(stmt)
        current = result.scalar_one_or_none()
        if current is None:
            return ancestors

        current_id = current.parent_id
        visited: set[uuid.UUID] = {entity_id}

        while current_id is not None and current_id not in visited:
            visited.add(current_id)
            stmt = select(LegalEntity).where(LegalEntity.id == current_id)
            result = await session.execute(stmt)
            parent = result.scalar_one_or_none()
            if parent is None:
                break
            ancestors.append(parent)
            current_id = parent.parent_id

        return ancestors

    @staticmethod
    async def get_descendants(
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> list[LegalEntity]:
        """Return all descendants (children, grandchildren, ...) recursively.

        Uses iterative BFS.  The entity itself is **not** included.
        """
        descendants: list[LegalEntity] = []
        queue: list[uuid.UUID] = [entity_id]
        visited: set[uuid.UUID] = {entity_id}

        while queue:
            parent_id = queue.pop(0)
            stmt = select(LegalEntity).where(
                LegalEntity.parent_id == parent_id,
            )
            result = await session.execute(stmt)
            children = list(result.scalars().all())
            for child in children:
                if child.id not in visited:
                    visited.add(child.id)
                    descendants.append(child)
                    queue.append(child.id)

        return descendants

    @staticmethod
    async def get_root(
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> LegalEntity | None:
        """Return the top-level ancestor (root) of the entity.

        If the entity itself has no parent, it **is** the root.
        """
        stmt = select(LegalEntity).where(LegalEntity.id == entity_id)
        result = await session.execute(stmt)
        current = result.scalar_one_or_none()
        if current is None:
            return None

        visited: set[uuid.UUID] = {entity_id}

        while current.parent_id is not None and current.parent_id not in visited:
            visited.add(current.parent_id)
            stmt = select(LegalEntity).where(LegalEntity.id == current.parent_id)
            result = await session.execute(stmt)
            parent = result.scalar_one_or_none()
            if parent is None:
                break
            current = parent

        return current

    @staticmethod
    async def get_siblings(
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> list[LegalEntity]:
        """Return entities sharing the same parent (excluding self).

        Top-level entities (parent_id IS NULL) are siblings of each other.
        """
        stmt = select(LegalEntity).where(LegalEntity.id == entity_id)
        result = await session.execute(stmt)
        entity = result.scalar_one_or_none()
        if entity is None:
            return []

        if entity.parent_id is None:
            stmt = select(LegalEntity).where(
                LegalEntity.parent_id.is_(None),
                LegalEntity.id != entity_id,
            )
        else:
            stmt = select(LegalEntity).where(
                LegalEntity.parent_id == entity.parent_id,
                LegalEntity.id != entity_id,
            )

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def move_entity(
        session: AsyncSession,
        entity_id: uuid.UUID,
        new_parent_id: uuid.UUID | None,
    ) -> LegalEntity:
        """Re-parent an entity to a new parent.

        Raises ``ValueError`` if the move would create a cycle.
        """
        stmt = select(LegalEntity).where(LegalEntity.id == entity_id)
        result = await session.execute(stmt)
        entity = result.scalar_one_or_none()
        if entity is None:
            msg = f"Entity {entity_id} not found"
            raise ValueError(msg)

        # Prevent cycles: new_parent must not be a descendant of entity
        if new_parent_id is not None:
            descendants = await EntityTree.get_descendants(session, entity_id)
            descendant_ids = {d.id for d in descendants}
            if new_parent_id in descendant_ids:
                msg = f"Cannot move entity {entity_id} under {new_parent_id}: would create a cycle"
                raise ValueError(msg)

            # Verify new parent exists
            stmt = select(LegalEntity).where(LegalEntity.id == new_parent_id)
            result = await session.execute(stmt)
            new_parent = result.scalar_one_or_none()
            if new_parent is None:
                msg = f"New parent entity {new_parent_id} not found"
                raise ValueError(msg)

        old_parent_id = entity.parent_id
        entity.parent_id = new_parent_id
        await session.flush()

        logger.info(
            "entity_moved",
            entity_id=str(entity_id),
            old_parent_id=str(old_parent_id) if old_parent_id else None,
            new_parent_id=str(new_parent_id) if new_parent_id else None,
        )
        return entity
