"""Audit middleware — automatically log write operations."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from rupiv.db import get_db

logger = structlog.get_logger(__name__)

# HTTP methods that mutate state
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths to skip (health checks, metrics, auth, etc.)
_SKIP_PREFIXES = ("/health", "/metrics", "/docs", "/openapi.json", "/redoc")

# Sensitive resource paths where GET operations should also be audited
_SENSITIVE_READ_PATTERNS = (
    "/v1/customers/",
    "/v1/invoices/",
    "/v1/portal/invoices/",
    "/v1/payment-methods",
    "/v1/webhook-endpoints",
)


class AuditMiddleware(BaseHTTPMiddleware):
    """Fire-and-forget audit logging for every write request.

    Extracts actor, resource, and action from the request path and method,
    then spawns an ``asyncio.create_task`` so the response is never delayed
    by the audit write.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        is_write = request.method in _WRITE_METHODS
        is_sensitive_read = (
            request.method == "GET"
            and any(request.url.path.startswith(p) for p in _SENSITIVE_READ_PATTERNS)
        )

        if not is_write and not is_sensitive_read:
            return response

        if any(request.url.path.startswith(p) for p in _SKIP_PREFIXES):
            return response

        # Only log successful mutations (2xx)
        if not (200 <= response.status_code < 300):
            return response

        asyncio.create_task(
            _record_audit(request, response),
        )

        return response


async def _record_audit(request: Request, response: Response) -> None:
    """Background task that writes the audit row."""
    try:
        from rupiv.compliance.audit import log_action

        path_parts = [p for p in request.url.path.strip("/").split("/") if p]

        # Derive resource_type and action from the path + method
        # e.g. POST /v1/customers -> resource_type=customers, action=create
        resource_type = path_parts[-1] if path_parts else "unknown"
        resource_id_str: str | None = None

        # If the last segment looks like a UUID, treat the previous segment
        # as resource_type
        if len(path_parts) >= 2:
            try:
                uuid.UUID(path_parts[-1])
                resource_id_str = path_parts[-1]
                resource_type = path_parts[-2]
            except ValueError:
                pass

        action_map: dict[str, str] = {
            "GET": "read",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
        }
        action = action_map.get(request.method, request.method.lower())

        # Best-effort actor extraction from headers / state
        actor_id_header = request.headers.get("x-actor-id")
        actor_id: uuid.UUID
        if actor_id_header:
            try:
                actor_id = uuid.UUID(actor_id_header)
            except ValueError:
                actor_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        else:
            actor_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

        resource_id: uuid.UUID
        if resource_id_str:
            resource_id = uuid.UUID(resource_id_str)
        else:
            resource_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        # Use a fresh session for the background write
        async for session in get_db():
            await log_action(
                session,
                actor_id=actor_id,
                actor_type="api",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                },
            )
            break  # get_db is an async generator; we only need one session

    except Exception:
        # Never let audit failures break the request flow
        logger.exception("audit.middleware_error")
