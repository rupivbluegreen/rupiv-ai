"""ViDA (VAT in the Digital Age) reporting stub.

The EU ViDA regulation introduces mandatory real-time digital reporting
for intra-community B2B transactions. The full mandate takes effect in
2028. This module provides a stub implementation that records transaction
data and logs that reporting is not yet live.

TODO(2028): Implement actual ViDA XML/JSON reporting format once the
    European Commission publishes the final technical specification.
TODO(2028): Connect to the national tax authority's ViDA endpoint for
    real-time submission.
TODO(2028): Add digital reporting requirements for e-invoicing (CTC model).
TODO(2028): Implement the ViDA "deemed supplier" rules for platform operators.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ViDAReport:
    """Result of a ViDA transaction report submission."""

    report_id: str
    """Unique identifier for the report (UUID)."""

    status: str
    """Current status: ``"stub"`` until ViDA goes live in 2028."""

    submitted_at: datetime
    """Timestamp when the report was recorded."""


class ViDAReporter:
    """Stub reporter for ViDA real-time digital reporting.

    TODO(2028): Replace stub implementation with actual ViDA API calls
        when the mandate goes live. The reporter should submit structured
        e-invoicing data to the national tax authority in near-real-time.
    """

    def __init__(self) -> None:
        self._reports: list[ViDAReport] = []

    def report_transaction(self, invoice_data: dict[str, Any]) -> ViDAReport:
        """Record a transaction for future ViDA reporting.

        Currently a stub that logs the data and returns a placeholder
        report. When ViDA goes live in 2028, this will submit the
        transaction to the relevant tax authority's digital reporting
        system.

        Args:
            invoice_data: Invoice data dict containing at minimum
                ``invoice_id``, ``seller_country``, ``buyer_country``,
                ``tax_amount``, and ``total``.

        Returns:
            A :class:`ViDAReport` with status ``"stub"``.
        """
        report = ViDAReport(
            report_id=str(uuid.uuid4()),
            status="stub",
            submitted_at=datetime.now(timezone.utc),
        )

        self._reports.append(report)

        # TODO(2028): Replace this log with actual API submission.
        log.info(
            "vida.transaction_recorded",
            report_id=report.report_id,
            status=report.status,
            invoice_id=invoice_data.get("invoice_id"),
            seller_country=invoice_data.get("seller_country"),
            buyer_country=invoice_data.get("buyer_country"),
            message="ViDA reporting is not yet live. Data recorded for future compliance.",
        )

        return report
