"""Multi-currency support with ECB daily exchange rates."""

from __future__ import annotations

import time
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# ECB base URL (for future live fetching)
# ---------------------------------------------------------------------------
ECB_RATE_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A"
)

# ---------------------------------------------------------------------------
# Hardcoded MVP rate table — rates are "1 EUR = X foreign currency"
# Source: ECB reference rates (approximate, for MVP only)
# ---------------------------------------------------------------------------
_MVP_RATES: dict[str, Decimal] = {
    "EUR": Decimal("1.0000"),
    "USD": Decimal("1.0850"),
    "GBP": Decimal("0.8560"),
    "CHF": Decimal("0.9420"),
    "SEK": Decimal("11.2500"),
    "DKK": Decimal("7.4600"),
    "PLN": Decimal("4.3200"),
    "CZK": Decimal("25.2500"),
    "HUF": Decimal("395.0000"),
    "RON": Decimal("4.9770"),
    "BGN": Decimal("1.9558"),
    "NOK": Decimal("11.6500"),
    "JPY": Decimal("163.5000"),
    "KRW": Decimal("1450.0000"),
    "CAD": Decimal("1.4700"),
    "AUD": Decimal("1.6500"),
}

# Currencies with 0 decimal places
_ZERO_DECIMAL_CURRENCIES: frozenset[str] = frozenset({
    "JPY", "KRW", "VND", "CLP", "ISK", "UGX", "RWF",
})

# Cache TTL: 24 hours in seconds
_CACHE_TTL_SECONDS: int = 86_400


# ---------------------------------------------------------------------------
# Rounding helper
# ---------------------------------------------------------------------------


def round_currency(amount: Decimal, currency: str) -> Decimal:
    """Round an amount to the correct number of decimal places for a currency.

    Most currencies use 2 decimal places.  JPY, KRW, etc. use 0.
    """
    currency = currency.upper()
    if currency in _ZERO_DECIMAL_CURRENCIES:
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# ECB Rate Provider
# ---------------------------------------------------------------------------


class ECBRateProvider:
    """Currency conversion using ECB reference rates.

    All conversions go through EUR as the base (pivot) currency.

    For the MVP the provider uses a hardcoded rate table.  ``fetch_rates``
    is a stub that returns the same table but will be replaced with a live
    HTTP call to the ECB Data API in production.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Decimal] = {}
        self._cache_timestamp: float = 0.0

    # ----- Cache management -----

    def _cache_is_fresh(self) -> bool:
        """Return True if the in-memory cache is younger than 24 h."""
        return (
            bool(self._cache)
            and (time.monotonic() - self._cache_timestamp) < _CACHE_TTL_SECONDS
        )

    def _populate_cache(self, rates: dict[str, Decimal]) -> None:
        self._cache = dict(rates)
        self._cache_timestamp = time.monotonic()

    # ----- Rate fetching -----

    async def fetch_rates(
        self,
        ref_date: date | None = None,
    ) -> dict[str, Decimal]:
        """Fetch exchange rates from the ECB.

        For the MVP, returns the hardcoded rate table.  *ref_date* is
        accepted for API compatibility but currently ignored.
        """
        # In production, this would be an async HTTP call:
        #   async with httpx.AsyncClient() as client:
        #       resp = await client.get(ECB_RATE_URL, params={...})
        #       rates = _parse_ecb_response(resp)
        rates = dict(_MVP_RATES)
        self._populate_cache(rates)

        logger.debug(
            "ecb_rates_fetched",
            currency_count=len(rates),
            ref_date=str(ref_date) if ref_date else "latest",
        )
        return rates

    async def _ensure_rates(self) -> dict[str, Decimal]:
        """Return cached rates, fetching if stale or empty."""
        if self._cache_is_fresh():
            return self._cache
        return await self.fetch_rates()

    # ----- Conversion -----

    async def get_rate(
        self,
        from_ccy: str,
        to_ccy: str,
        ref_date: date | None = None,
    ) -> Decimal:
        """Return the exchange rate from *from_ccy* to *to_ccy*.

        Both legs go through EUR:
            rate = (1 / EUR→from_ccy) * EUR→to_ccy
        """
        from_ccy = from_ccy.upper()
        to_ccy = to_ccy.upper()

        if from_ccy == to_ccy:
            return Decimal("1.0000")

        rates = await self._ensure_rates()

        from_rate = rates.get(from_ccy)
        to_rate = rates.get(to_ccy)

        if from_rate is None:
            msg = f"Unsupported currency: {from_ccy}"
            raise ValueError(msg)
        if to_rate is None:
            msg = f"Unsupported currency: {to_ccy}"
            raise ValueError(msg)

        # from_ccy → EUR → to_ccy
        return (to_rate / from_rate).quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        )

    async def convert(
        self,
        amount: Decimal,
        from_ccy: str,
        to_ccy: str,
        ref_date: date | None = None,
    ) -> Decimal:
        """Convert *amount* from one currency to another.

        The result is rounded according to the target currency's rules.
        """
        rate = await self.get_rate(from_ccy, to_ccy, ref_date)
        converted = amount * rate
        return round_currency(converted, to_ccy)
