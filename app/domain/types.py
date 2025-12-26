"""Shared types and enums for the domain layer."""

from enum import Enum


class AccountType(str, Enum):
    """Types of accounts in the chart of accounts."""

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class UserRole(str, Enum):
    """Roles for user access within a company."""

    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"
