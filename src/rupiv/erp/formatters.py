"""Export formatters for journal entries to ERP systems.

Converts ``JournalEntry`` objects into CSV, QuickBooks IIF, or Xero CSV format.
Each formatter applies an optional GL account mapping to translate internal
account codes to the customer's chart of accounts.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from rupiv.revenue_recognition.journal import JournalEntry


def _map_account(account: str, mapping: dict[str, str] | None) -> str:
    """Translate an internal GL code using the mapping, or return as-is."""
    if mapping and account in mapping:
        return mapping[account]
    return account


# ---------------------------------------------------------------------------
# Generic CSV
# ---------------------------------------------------------------------------


def to_csv(
    entries: list[JournalEntry],
    gl_mapping: dict[str, str] | None = None,
) -> str:
    """Format journal entries as generic CSV.

    Columns: date, debit_account, credit_account, amount, currency, description, reference_id
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "date",
        "debit_account",
        "credit_account",
        "amount",
        "currency",
        "description",
        "reference_id",
    ])

    for entry in entries:
        writer.writerow([
            entry.date.isoformat(),
            _map_account(entry.debit_account, gl_mapping),
            _map_account(entry.credit_account, gl_mapping),
            str(entry.amount),
            entry.currency,
            entry.description,
            str(entry.reference_id),
        ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# QuickBooks IIF
# ---------------------------------------------------------------------------


def to_quickbooks_iif(
    entries: list[JournalEntry],
    gl_mapping: dict[str, str] | None = None,
) -> str:
    """Format journal entries as QuickBooks IIF (Intuit Interchange Format).

    Each journal entry becomes a TRNS/SPL pair:
    - TRNS line: the debit side
    - SPL line: the credit side
    - ENDTRNS marker
    """
    lines: list[str] = []
    # Header
    lines.append("!TRNS\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tMEMO")
    lines.append("!SPL\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tMEMO")
    lines.append("!ENDTRNS")

    for entry in entries:
        date_str = entry.date.strftime("%m/%d/%Y")
        debit = _map_account(entry.debit_account, gl_mapping)
        credit = _map_account(entry.credit_account, gl_mapping)
        memo = entry.description.replace("\t", " ")

        # Debit line (positive amount)
        lines.append(f"TRNS\tGENERAL JOURNAL\t{date_str}\t{debit}\t{entry.amount}\t{memo}")
        # Credit line (negative amount)
        lines.append(f"SPL\tGENERAL JOURNAL\t{date_str}\t{credit}\t-{entry.amount}\t{memo}")
        lines.append("ENDTRNS")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Xero CSV
# ---------------------------------------------------------------------------


def to_xero_csv(
    entries: list[JournalEntry],
    gl_mapping: dict[str, str] | None = None,
) -> str:
    """Format journal entries as Xero manual journal CSV import.

    Xero expects: *Narration, Date, Account Code, Debit, Credit, Description
    Each journal entry produces two rows (debit + credit).
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "*Narration",
        "Date",
        "Account Code",
        "Debit",
        "Credit",
        "Description",
    ])

    for entry in entries:
        date_str = entry.date.strftime("%d/%m/%Y")
        narration = entry.description
        debit_acct = _map_account(entry.debit_account, gl_mapping)
        credit_acct = _map_account(entry.credit_account, gl_mapping)

        # Debit row
        writer.writerow([narration, date_str, debit_acct, str(entry.amount), "", ""])
        # Credit row
        writer.writerow([narration, date_str, credit_acct, "", str(entry.amount), ""])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_FORMATTERS: dict[str, Any] = {
    "csv": to_csv,
    "quickbooks": to_quickbooks_iif,
    "xero": to_xero_csv,
}


def format_entries(
    provider: str,
    entries: list[JournalEntry],
    gl_mapping: dict[str, str] | None = None,
) -> str:
    """Format journal entries for the given provider.

    Raises ``ValueError`` if the provider is not supported.
    """
    formatter = _FORMATTERS.get(provider)
    if formatter is None:
        msg = f"Unsupported ERP provider: {provider}. Supported: {list(_FORMATTERS.keys())}"
        raise ValueError(msg)
    result: str = formatter(entries, gl_mapping)
    return result
