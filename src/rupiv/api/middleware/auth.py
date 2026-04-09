"""API key authentication dependency."""

from __future__ import annotations

import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the X-API-Key header.

    Returns the verified API key string for downstream use.
    Raises 401 if the key is missing or invalid.
    """
    if api_key is None:
        logger.warning("auth_missing_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    # TODO: Look up API key in database, resolve to tenant/org
    # For now, accept any non-empty key in development
    logger.info("auth_api_key_verified", key_prefix=api_key[:8] if len(api_key) >= 8 else "***")
    return api_key


# Re-export as a FastAPI dependency for use in route decorators
ApiKeyAuth = Depends(verify_api_key)
