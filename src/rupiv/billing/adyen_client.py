"""Adyen SEPA credit transfer client.

Wraps the Adyen Payment API (v68) for initiating and querying SEPA
credit transfers used in agent-to-agent (A2A) settlements.

Amounts are converted to minor units (cents) as required by Adyen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

ADYEN_BASE_URL = "https://pal-test.adyen.com/pal/servlet/Payment/v68"

# Currency -> minor-unit exponent.  EUR/USD = 2 (cents), JPY = 0, etc.
_MINOR_UNIT_EXPONENTS: dict[str, int] = {
    "EUR": 2,
    "USD": 2,
    "GBP": 2,
    "CHF": 2,
    "SEK": 2,
    "NOK": 2,
    "DKK": 2,
    "PLN": 2,
    "CZK": 2,
    "JPY": 0,
}


def _to_minor_units(amount: Decimal, currency: str) -> int:
    """Convert a Decimal amount to Adyen minor units (e.g. EUR 12.50 -> 1250)."""
    exponent = _MINOR_UNIT_EXPONENTS.get(currency.upper(), 2)
    return int(amount * (10 ** exponent))


def _from_minor_units(minor: int, currency: str) -> Decimal:
    """Convert Adyen minor units back to a Decimal amount."""
    exponent = _MINOR_UNIT_EXPONENTS.get(currency.upper(), 2)
    return Decimal(minor) / (10 ** exponent)


@dataclass(frozen=True)
class AdyenTransfer:
    """Result of an Adyen SEPA transfer request or status query."""

    psp_reference: str
    status: str  # "Authorised" | "Refused" | "Pending"
    amount: Decimal
    currency: str
    reference: str


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AdyenClient:
    """Async HTTP client for the Adyen Payment API.

    Uses ``X-API-Key`` header authentication and targets the test
    environment by default.

    Args:
        api_key: Adyen API key.
        merchant_account: Adyen merchant account identifier.
        base_url: Override the default Adyen test URL if needed.
    """

    def __init__(
        self,
        api_key: str,
        merchant_account: str,
        *,
        base_url: str = ADYEN_BASE_URL,
    ) -> None:
        self._merchant_account = merchant_account
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # SEPA transfer
    # ------------------------------------------------------------------

    async def create_sepa_transfer(
        self,
        amount: Decimal,
        currency: str,
        iban: str,
        bic: str | None,
        reference: str,
        description: str,
    ) -> AdyenTransfer:
        """Initiate a SEPA credit transfer via Adyen.

        Args:
            amount: Transfer amount as Decimal.
            currency: ISO-4217 currency code (typically ``"EUR"``).
            iban: Creditor IBAN.
            bic: Creditor BIC (optional for SEPA zone).
            reference: Unique payment reference (idempotency).
            description: Human-readable description for the bank statement.

        Returns:
            An ``AdyenTransfer`` with the PSP reference and status.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses from Adyen.
        """
        minor_amount = _to_minor_units(amount, currency)

        bank_account: dict[str, Any] = {
            "iban": iban,
            "ownerName": "Agent Account",
            "countryCode": iban[:2].upper(),
        }
        if bic:
            bank_account["bic"] = bic

        payload: dict[str, Any] = {
            "merchantAccount": self._merchant_account,
            "amount": {
                "value": minor_amount,
                "currency": currency.upper(),
            },
            "reference": reference,
            "paymentMethod": {
                "type": "sepadirectdebit",
                "sepa.ibanNumber": iban,
                "sepa.ownerName": "Agent Account",
            },
            "bankAccount": bank_account,
            "shopperStatement": description,
        }

        log.info(
            "adyen.create_sepa_transfer",
            reference=reference,
            amount=str(amount),
            currency=currency,
            iban_last4=iban[-4:],
        )

        response = await self._http.post("/payments", json=payload)
        response.raise_for_status()
        data = response.json()

        status = data.get("resultCode", "Pending")
        psp_ref = data.get("pspReference", "")

        transfer = AdyenTransfer(
            psp_reference=psp_ref,
            status=status,
            amount=amount,
            currency=currency.upper(),
            reference=reference,
        )

        log.info(
            "adyen.transfer_result",
            psp_reference=psp_ref,
            status=status,
            reference=reference,
        )
        return transfer

    # ------------------------------------------------------------------
    # Status query
    # ------------------------------------------------------------------

    async def get_transfer_status(self, psp_reference: str) -> AdyenTransfer:
        """Query the status of an existing transfer by PSP reference.

        Args:
            psp_reference: The Adyen PSP reference returned from
                ``create_sepa_transfer``.

        Returns:
            An ``AdyenTransfer`` with the current status.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses from Adyen.
        """
        log.info("adyen.get_transfer_status", psp_reference=psp_reference)

        payload: dict[str, Any] = {
            "merchantAccount": self._merchant_account,
            "pspReference": psp_reference,
        }

        response = await self._http.post(
            "/payments/details",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        status = data.get("resultCode", "Pending")
        amount_data = data.get("amount", {})
        currency = amount_data.get("currency", "EUR")
        minor_value = amount_data.get("value", 0)

        return AdyenTransfer(
            psp_reference=psp_reference,
            status=status,
            amount=_from_minor_units(minor_value, currency),
            currency=currency,
            reference=data.get("merchantReference", ""),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
