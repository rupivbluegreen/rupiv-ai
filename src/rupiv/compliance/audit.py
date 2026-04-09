"""Audit trail operations — log, query, and export audit entries."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.audit_log import AuditLog

logger = structlog.get_logger(__name__)


async def log_action(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    actor_type: str,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    changes: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Create an append-only audit log entry.

    This is the single entry-point for recording any auditable action.
    """
    entry = AuditLog(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=changes,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_=metadata,
    )
    session.add(entry)
    await session.flush()

    logger.info(
        "audit.logged",
        actor_id=str(actor_id),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
    )
    return entry


async def get_audit_trail(
    session: AsyncSession,
    *,
    resource_type: str,
    resource_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    """Return the audit trail for a specific resource, newest first."""
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == resource_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_actor_trail(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    """Return all actions performed by a given actor, newest first."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.actor_id == actor_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def export_audit_logs(
    session: AsyncSession,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    resource_type: str | None = None,
    action: str | None = None,
    limit: int = 10_000,
) -> str:
    """Export audit logs as CSV for compliance reporting.

    Returns a UTF-8 CSV string.  Callers can stream this to an HTTP response
    or write it to object storage.
    """
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)

    if start is not None:
        stmt = stmt.where(AuditLog.timestamp >= start)
    if end is not None:
        stmt = stmt.where(AuditLog.timestamp <= end)
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)

    result = await session.execute(stmt)
    logs = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id",
        "timestamp",
        "actor_id",
        "actor_type",
        "action",
        "resource_type",
        "resource_id",
        "changes",
        "ip_address",
        "user_agent",
    ])
    for log in logs:
        writer.writerow([
            str(log.id),
            log.timestamp.isoformat(),
            str(log.actor_id),
            log.actor_type,
            log.action,
            log.resource_type,
            str(log.resource_id),
            str(log.changes) if log.changes else "",
            log.ip_address or "",
            log.user_agent or "",
        ])

    return buf.getvalue()
