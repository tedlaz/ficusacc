"""Transaction repository interface."""

from abc import abstractmethod
from datetime import date
from typing import Any

from app.domain.repositories.base import ITenantRepository

# Type alias - actual type is TransactionModel
Transaction = Any


class ITransactionRepository(ITenantRepository[Transaction]):
    """
    Repository interface for Transaction entities.

    Provides transaction-specific query operations in addition
    to the base tenant-aware CRUD operations.
    """

    @abstractmethod
    async def get_with_lines(self, transaction_id: int, company_id: int) -> Transaction | None:
        """Get a transaction with all its lines loaded."""
        pass

    @abstractmethod
    async def get_by_date_range(
        self, company_id: int, start_date: date, end_date: date
    ) -> list[Transaction]:
        """Get all transactions within a date range."""
        pass

    @abstractmethod
    async def get_by_account(
        self,
        company_id: int,
        account_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Transaction]:
        """Get all transactions that include a specific account."""
        pass

    @abstractmethod
    async def get_posted(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[Transaction]:
        """Get all posted transactions for a company."""
        pass

    @abstractmethod
    async def get_unposted(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[Transaction]:
        """Get all unposted (draft) transactions for a company."""
        pass
