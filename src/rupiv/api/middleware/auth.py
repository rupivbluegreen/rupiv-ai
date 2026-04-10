"""API key and JWT authentication dependencies."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.config import get_settings
from rupiv.db import get_db
from rupiv.models.api_key import ApiKey
from rupiv.models.customer import Customer
from rupiv.models.customer_user import CustomerUser

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
# Clerk JWT verification via JWKS
# ---------------------------------------------------------------------------

_jwks_cache: dict[str, Any] | None = None
_jwks_cache_ts: float = 0.0
_JWKS_CACHE_TTL_SECONDS: float = 900.0  # 15 minutes


async def _fetch_clerk_jwks() -> dict[str, Any]:
    """Fetch Clerk's JWKS, with in-memory caching (1h TTL)."""
    global _jwks_cache, _jwks_cache_ts  # noqa: PLW0603

    now = datetime.now(UTC).timestamp()
    if _jwks_cache is not None and (now - _jwks_cache_ts) < _JWKS_CACHE_TTL_SECONDS:
        return _jwks_cache

    settings = get_settings()
    jwks_url = settings.CLERK_JWKS_URL
    if not jwks_url:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="CLERK_JWKS_URL not configured — JWT auth unavailable",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            fetched: dict[str, Any] = resp.json()
            _jwks_cache = fetched
            _jwks_cache_ts = now
            return fetched
    except httpx.HTTPError as exc:
        logger.error("clerk_jwks_fetch_failed", error=str(exc))
        if _jwks_cache is not None:
            return _jwks_cache  # stale cache better than failure
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch Clerk JWKS for JWT verification",
        ) from exc


def _find_signing_key(jwks: dict[str, Any], token: str) -> dict[str, Any]:
    """Find the JWK matching the token's ``kid`` header."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed JWT header",
        ) from exc

    kid = unverified_header.get("kid")
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="JWT signing key not found in JWKS",
    )


async def verify_jwt(token: str) -> dict[str, Any]:
    """Verify a Clerk-issued JWT and return its claims."""
    jwks = await _fetch_clerk_jwks()
    signing_key = _find_signing_key(jwks, token)

    try:
        settings = get_settings()
        decode_options: dict[str, bool] = {}
        audience: str | None = None

        # If CLERK_AUDIENCE is configured, enforce audience validation.
        # Otherwise skip for backward compat with existing Clerk setups.
        if hasattr(settings, "CLERK_AUDIENCE") and settings.CLERK_AUDIENCE:
            audience = settings.CLERK_AUDIENCE
        else:
            decode_options["verify_aud"] = False

        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audience,
            options=decode_options,
        )
    except JWTError as exc:
        logger.warning("auth_jwt_verification_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired JWT",
        ) from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT missing 'sub' claim",
        )

    logger.info("auth_jwt_verified", sub=sub)
    return claims


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
        claims = await verify_jwt(bearer.credentials)
        sub: str = claims["sub"]

        # Resolve Clerk user ID to a CustomerUser → Customer
        cu_result = await session.execute(
            select(CustomerUser).where(CustomerUser.clerk_user_id == sub),
        )
        customer_user: CustomerUser | None = cu_result.scalar_one_or_none()

        if customer_user is None:
            logger.warning("auth_jwt_no_customer_user", clerk_user_id=sub)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No customer account linked to this user. Complete onboarding first.",
            )

        customer_result = await session.execute(
            select(Customer).where(Customer.id == customer_user.customer_id),
        )
        customer = customer_result.scalar_one_or_none()
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer associated with user no longer exists",
            )

        request.state.customer_user = customer_user
        return customer

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
