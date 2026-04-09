"""Compliance API — audit logs, GDPR data export, anonymization."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.compliance.audit import (
    export_audit_logs,
    get_audit_trail,
)
from rupiv.compliance.data_export import (
    anonymize_customer,
    export_customer_data,
    get_data_retention_report,
)
from rupiv.db import get_db

router = APIRouter(prefix="/compliance", tags=["compliance"])


# -------------------------------------------------------------------------
# Audit log endpoints
# -------------------------------------------------------------------------


@router.get("/audit-logs")
async def list_audit_logs(
    start: datetime | None = Query(None, description="ISO 8601 start timestamp"),
    end: datetime | None = Query(None, description="ISO 8601 end timestamp"),
    resource_type: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=10_000),
    format: str = Query("json", regex="^(json|csv)$"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """List audit logs with optional filters.

    Supports JSON (default) or CSV export via ``?format=csv``.
    """
    if format == "csv":
        csv_data = await export_audit_logs(
            session,
            start=start,
            end=end,
            resource_type=resource_type,
            action=action,
            limit=limit,
        )
        return PlainTextResponse(csv_data, media_type="text/csv")

    from rupiv.compliance.audit import get_actor_trail  # noqa: F811
    from sqlalchemy import select

    from rupiv.models.audit_log import AuditLog

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

    return [
        {
            "id": str(log.id),
            "timestamp": log.timestamp.isoformat(),
            "actor_id": str(log.actor_id),
            "actor_type": log.actor_type,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id),
            "changes": log.changes,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "metadata": log.metadata_,
        }
        for log in logs
    ]


@router.get("/audit-logs/{resource_type}/{resource_id}")
async def get_resource_audit_trail(
    resource_type: str,
    resource_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=10_000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get the full audit trail for a specific resource."""
    logs = await get_audit_trail(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": str(log.id),
            "timestamp": log.timestamp.isoformat(),
            "actor_id": str(log.actor_id),
            "actor_type": log.actor_type,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id),
            "changes": log.changes,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
        }
        for log in logs
    ]


# -------------------------------------------------------------------------
# GDPR / data compliance endpoints
# -------------------------------------------------------------------------

_SYSTEM_ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000000")


@router.post("/data-export/{customer_id}")
async def data_export(
    customer_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """GDPR portable data export for a customer."""
    try:
        return await export_customer_data(
            session, customer_id, actor_id=_SYSTEM_ACTOR
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/anonymize/{customer_id}")
async def anonymize(
    customer_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Anonymize a customer's PII (GDPR right to erasure)."""
    try:
        return await anonymize_customer(
            session, customer_id, actor_id=_SYSTEM_ACTOR
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/retention-report")
async def retention_report(
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Data retention overview for compliance audits."""
    return await get_data_retention_report(session)
