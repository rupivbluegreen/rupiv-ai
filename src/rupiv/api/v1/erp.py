"""ERP integration endpoints — connection management and journal entry export."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.api.middleware.auth import get_current_api_key
from rupiv.db import get_db
from rupiv.erp.formatters import format_entries
from rupiv.models.api_key import ApiKey
from rupiv.models.erp_connection import ERPConnection, ExportLog
from rupiv.revenue_recognition.journal import JournalEntry, generate_journal_entries
from rupiv.revenue_recognition.schedules import RevenueScheduleEntry

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/erp", tags=["erp"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ERPConnectionResponse(BaseModel):
    """ERP connection resource."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    name: str
    gl_account_mapping: dict[str, str] | None = None
    is_active: bool
    last_sync_at: datetime | None = None
    created_at: datetime


class ERPConnectionCreate(BaseModel):
    """Request body for creating an ERP connection."""

    provider: str = Field(pattern=r"^(quickbooks|xero|csv)$")
    name: str = Field(min_length=1, max_length=255)
    gl_account_mapping: dict[str, str] | None = None


class ERPConnectionUpdate(BaseModel):
    """Request body for updating an ERP connection."""

    name: str | None = None
    gl_account_mapping: dict[str, str] | None = None
    is_active: bool | None = None


class ExportRequest(BaseModel):
    """Request body for triggering a journal entry export."""

    connection_id: uuid.UUID
    period: str = Field(
        pattern=r"^\d{4}-\d{2}$",
        description="YYYY-MM format",
    )


class ExportLogResponse(BaseModel):
    """Export log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    erp_connection_id: uuid.UUID
    period: str
    entry_count: int
    status: str
    error_message: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Connection CRUD
# ---------------------------------------------------------------------------


@router.get("/connections", response_model=list[ERPConnectionResponse])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> list[ERPConnectionResponse]:
    """List all ERP connections."""
    result = await db.execute(select(ERPConnection).order_by(ERPConnection.created_at.desc()))
    connections = result.scalars().all()
    return [ERPConnectionResponse.model_validate(c) for c in connections]


@router.post(
    "/connections",
    response_model=ERPConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_connection(
    payload: ERPConnectionCreate,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> ERPConnectionResponse:
    """Create a new ERP connection."""
    conn = ERPConnection(
        provider=payload.provider,
        name=payload.name,
        gl_account_mapping=payload.gl_account_mapping,
        is_active=True,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return ERPConnectionResponse.model_validate(conn)


@router.patch("/connections/{conn_id}", response_model=ERPConnectionResponse)
async def update_connection(
    conn_id: uuid.UUID,
    payload: ERPConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> ERPConnectionResponse:
    """Update an ERP connection."""
    result = await db.execute(select(ERPConnection).where(ERPConnection.id == conn_id))
    conn: ERPConnection | None = result.scalar_one_or_none()

    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(conn, key, value)
    await db.flush()
    await db.refresh(conn)

    return ERPConnectionResponse.model_validate(conn)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.post("/export", summary="Export journal entries")
async def export_journal_entries(
    payload: ExportRequest,
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> PlainTextResponse:
    """Export journal entries for a period in the connection's format.

    Returns the formatted file as a plain-text download.
    """
    # Load connection
    result = await db.execute(
        select(ERPConnection).where(ERPConnection.id == payload.connection_id),
    )
    conn: ERPConnection | None = result.scalar_one_or_none()

    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    if not conn.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connection is inactive",
        )

    # Load revenue schedule entries for the period from DB
    from rupiv.models.revenue_schedule import RevenueEntry, RevenueSchedule

    schedules_result = await db.execute(select(RevenueSchedule))
    schedules = list(schedules_result.scalars().all())

    # Build schedule entries for the requested period
    schedule_entries: list[RevenueScheduleEntry] = []
    for schedule in schedules:
        entries_result = await db.execute(
            select(RevenueEntry).where(
                RevenueEntry.schedule_id == schedule.id,
                RevenueEntry.period == payload.period,
            ),
        )
        for entry in entries_result.scalars().all():
            schedule_entries.append(
                RevenueScheduleEntry(
                    period=entry.period,
                    recognized=entry.amount if entry.entry_type == "recognized" else 0,
                    deferred=entry.amount if entry.entry_type == "deferred" else 0,
                    gl_debit="1200-AR",
                    gl_credit="4000-saas-revenue",
                    method=schedule.method,
                    obligation_id=schedule.id,
                ),
            )

    # Generate journal entries
    journal_entries = generate_journal_entries(schedule_entries)

    # Format
    try:
        content = format_entries(
            provider=conn.provider,
            entries=journal_entries,
            gl_mapping=conn.gl_account_mapping,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Log the export
    export_log = ExportLog(
        erp_connection_id=conn.id,
        period=payload.period,
        entry_count=len(journal_entries),
        status="success",
    )
    db.add(export_log)

    # Content type based on provider
    content_type = "text/csv" if conn.provider in ("csv", "xero") else "text/plain"
    filename = f"journal-entries-{payload.period}.{conn.provider}"

    return PlainTextResponse(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Export logs
# ---------------------------------------------------------------------------


@router.get("/export-logs", response_model=list[ExportLogResponse])
async def list_export_logs(
    connection_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> list[ExportLogResponse]:
    """List export history."""
    stmt = select(ExportLog).order_by(ExportLog.created_at.desc()).limit(limit)
    if connection_id:
        stmt = stmt.where(ExportLog.erp_connection_id == connection_id)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [ExportLogResponse.model_validate(log) for log in logs]
