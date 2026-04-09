"""VIES API client for EU VAT ID validation.

Validates VAT identification numbers against the European Commission's
VIES REST API with in-memory caching (24h TTL) to avoid hammering the
service.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# VIES REST API endpoint
_VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"

# Cache TTL: 24 hours in seconds
_CACHE_TTL_SECONDS: int = 86_400

# HTTP timeout for VIES requests (seconds)
_VIES_TIMEOUT: float = 10.0


@dataclass(frozen=True)
class VatIdResult:
    """Result of a VAT ID validation against VIES."""

    valid: bool | None
    """``True`` if valid, ``False`` if invalid, ``None`` if VIES was
    unreachable and the result is unknown."""

    name: str | None
    """Registered business name (when available from VIES)."""

    address: str | None
    """Registered business address (when available from VIES)."""

    request_date: datetime
    """Timestamp of the validation request."""

    cached: bool
    """Whether this result was served from the local cache."""


# ---------------------------------------------------------------------------
# In-memory cache (MVP — replace with Redis for production)
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    result: VatIdResult
    expires_at: float  # monotonic time


_cache: dict[str, _CacheEntry] = {}


def _cache_key(country_code: str, vat_number: str) -> str:
    return f"{country_code}:{vat_number}"


def _get_cached(country_code: str, vat_number: str) -> VatIdResult | None:
    key = _cache_key(country_code, vat_number)
    entry = _cache.get(key)
    if entry is None:
        return None
    if time.monotonic() > entry.expires_at:
        _cache.pop(key, None)
        return None
    # Return a copy with cached=True
    return VatIdResult(
        valid=entry.result.valid,
        name=entry.result.name,
        address=entry.result.address,
        request_date=entry.result.request_date,
        cached=True,
    )


def _set_cached(country_code: str, vat_number: str, result: VatIdResult) -> None:
    key = _cache_key(country_code, vat_number)
    _cache[key] = _CacheEntry(
        result=result,
        expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
    )


def clear_cache() -> None:
    """Clear all cached VIES validation results (useful in tests)."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def validate_vat_id(
    country_code: str,
    vat_number: str,
) -> VatIdResult:
    """Validate an EU VAT ID against the VIES REST API.

    Results are cached in-memory for 24 hours to reduce load on the
    VIES service.

    Args:
        country_code: Two-letter EU country code (e.g. ``"DE"``).
        vat_number: The VAT number **without** the country prefix
            (e.g. ``"123456789"`` not ``"DE123456789"``).

    Returns:
        A :class:`VatIdResult`. If VIES is unreachable the ``valid``
        field will be ``None`` to indicate an unknown state.
    """
    # Check cache first
    cached = _get_cached(country_code, vat_number)
    if cached is not None:
        log.debug(
            "vies.cache_hit",
            country_code=country_code,
            vat_number=vat_number,
        )
        return cached

    request_date = datetime.now(timezone.utc)

    try:
        async with httpx.AsyncClient(timeout=_VIES_TIMEOUT) as client:
            response = await client.post(
                _VIES_URL,
                json={
                    "countryCode": country_code,
                    "vatNumber": vat_number,
                },
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()

        result = VatIdResult(
            valid=data.get("valid", False),
            name=data.get("name"),
            address=data.get("address"),
            request_date=request_date,
            cached=False,
        )

        log.info(
            "vies.validated",
            country_code=country_code,
            vat_number=vat_number,
            valid=result.valid,
        )

    except (httpx.HTTPError, httpx.TimeoutException, KeyError) as exc:
        # VIES is down or returned unexpected data — return unknown
        log.warning(
            "vies.unavailable",
            country_code=country_code,
            vat_number=vat_number,
            error=str(exc),
        )
        result = VatIdResult(
            valid=None,
            name=None,
            address=None,
            request_date=request_date,
            cached=False,
        )

    # Cache both successful and unknown results
    _set_cached(country_code, vat_number, result)
    return result
