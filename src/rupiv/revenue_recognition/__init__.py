"""IFRS 15 revenue recognition module for outcome-based billing.

Implements the five-step model:
1. Identify the contract (external — contract.py)
2. Identify performance obligations (obligations.py)
3. Determine the transaction price (variable_consideration.py)
4. Allocate the price to obligations (allocation.py)
5. Recognise revenue when obligations are satisfied (schedules.py, journal.py)
"""

from rupiv.revenue_recognition.allocation import AllocationResult, allocate_transaction_price
from rupiv.revenue_recognition.journal import JournalEntry, generate_journal_entries
from rupiv.revenue_recognition.obligations import (
    PerformanceObligation,
    identify_obligations,
)
from rupiv.revenue_recognition.schedules import RevenueScheduleEntry, generate_schedule
from rupiv.revenue_recognition.variable_consideration import (
    VariableEstimate,
    constrain_estimate,
    estimate_variable_consideration,
)

__all__ = [
    # Obligations
    "PerformanceObligation",
    "identify_obligations",
    # Allocation
    "AllocationResult",
    "allocate_transaction_price",
    # Schedules
    "RevenueScheduleEntry",
    "generate_schedule",
    # Variable consideration
    "VariableEstimate",
    "constrain_estimate",
    "estimate_variable_consideration",
    # Journal
    "JournalEntry",
    "generate_journal_entries",
]
