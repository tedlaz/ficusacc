"""Shared types and enums for the domain layer."""

from enum import Enum


class AccountType(str, Enum):
    """Types of accounts in the chart of accounts."""

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"

    @property
    def label(self) -> str:
        """Greek display name used throughout the UI and reports."""
        return ACCOUNT_TYPE_LABELS[self.value]


ACCOUNT_TYPE_LABELS = {
    "asset": "Ενεργητικό",
    "liability": "Υποχρεώσεις",
    "equity": "Καθαρή θέση",
    "revenue": "Έσοδα",
    "expense": "Έξοδα",
}
