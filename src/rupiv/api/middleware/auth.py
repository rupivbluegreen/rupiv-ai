"""API key and JWT authentication dependencies."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.db import get_db
from rupiv.models.api_key import ApiKey
from rupiv.models.customer import Customer

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Key generation helper
# ---------------------------------------------------------------------------


def generate_api_key(prefix: str = "rp_live_") -> tuple[str, str]:
    """Generate a new API key and its SHA-256 hash.

    Returns:
        A ``(full_key, key_hash)`` tuple.  The full key is returned to the
        caller exactly once; only the hash is persisted.
    """
    random_part = secrets.token_hex(16)  # 32 hex chars
    full_key = f"{prefix}{random_part}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_hash


def hash_api_key(key: str) -> str:
    """Return the SHA-256 hex digest of *key*."""
    return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Database verification
# ---------------------------------------------------------------------------


async def verify_api_key(key: str, session: AsyncSession) -> ApiKey:
    """Hash *key*, look it up in the database, and return the ``ApiKey`` row.

    Raises :class:`HTTPException` (401) when the key is invalid or inactive.
    Also updates ``last_used_at`` as a fire-and-forget side effect.
    """
    key_hash = hash_api_key(key)

    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    result = await session.execute(stmt)
    api_key: ApiKey | None = result.scalar_one_or_none()

    if api_key is None:
        logger.warning("auth_invalid_api_key", key_prefix=key[:12] if len(key) >= 12 else "***")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )

    # Update last_used_at (best-effort, don't fail the request)
    try:
        await session.execute(
            update(ApiKey)
            .where(ApiKey.id == api_key.id)
            .values(last_used_at=datetime.now(UTC)),
        )
    except Exception:
        logger.debug("auth_last_used_update_failed", api_key_id=str(api_key.id))

    logger.info(
        "auth_api_key_verified",
        api_key_id=str(api_key.id),
        customer_id=str(api_key.customer_id),
        key_prefix=api_key.key_prefix,
    )
    return api_key


# ---------------------------------------------------------------------------
# JWT stub (Clerk / Auth0 integration placeholder)
# ---------------------------------------------------------------------------


async def _verify_jwt_stub(token: str) -> dict:
    """Stub JWT verification — validates format only.

    Real Clerk/Auth0 verification will replace this function.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed JWT: expected three dot-separated segments",
        )
    logger.info("auth_jwt_stub_verified")
    return {"sub": "stub", "token": token}


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_customer(
    request: Request,
    api_key_value: str | None = Security(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> Customer:
    """Extract and verify credentials, returning the authenticated ``Customer``.

    Supports two auth methods (checked in order):
    1. ``X-API-Key`` header with an ``rp_live_`` / ``rp_test_`` prefixed key.
    2. ``Authorization: Bearer <jwt>`` header (dashboard sessions).

    Public endpoints (health, webhooks) should **not** depend on this.
    """
    # --- Path 1: API Key ---
    if api_key_value is not None:
        api_key = await verify_api_key(api_key_value, session)

        # Stash the ApiKey on the request state for downstream use
        request.state.api_key = api_key

        customer_result = await session.execute(
            select(Customer).where(Customer.id == api_key.customer_id),
        )
        customer: Customer | None = customer_result.scalar_one_or_none()
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer associated with API key no longer exists",
            )
        return customer

    # --- Path 2: Bearer JWT ---
    if bearer is not None:
        _claims = await _verify_jwt_stub(bearer.credentials)
        # TODO: Once Clerk/Auth0 is wired up, resolve claims["sub"] to a
        #       Customer row.  For now, return a 501 so callers know this
        #       path isn't fully implemented yet.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="JWT authentication is not yet fully implemented. Use an API key.",
        )

    # --- No credentials supplied ---
    logger.warning("auth_no_credentials")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication. Supply X-API-Key or Authorization: Bearer <jwt>.",
    )


async def get_current_api_key(
    api_key_value: str | None = Security(_api_key_header),
    session: AsyncSession = Depends(get_db),
) -> ApiKey:
    """Dependency that returns the verified ``ApiKey`` row directly.

    Useful for endpoints that need the key metadata (scopes, customer_id)
    without loading the full Customer.
    """
    if api_key_value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    return await verify_api_key(api_key_value, session)
