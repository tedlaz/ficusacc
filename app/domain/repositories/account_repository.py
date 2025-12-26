"""Account repository interface."""

from abc import abstractmethod
from typing import Any

from app.domain.repositories.base import ITenantRepository
from app.domain.types import AccountType


class IAccountRepository(ITenantRepository[Any]):
    """
    Repository interface for Account entities.

    Provides account-specific query operations in addition
    to the base tenant-aware CRUD operations.
    """

    @abstractmethod
    async def get_by_code(self, company_id: int, code: str) -> Any | None:
        """Get an account by its code within a company."""
        pass

    @abstractmethod
    async def get_by_type(self, company_id: int, account_type: AccountType) -> list[Any]:
        """Get all accounts of a specific type within a company."""
        pass

    @abstractmethod
    async def get_children(self, company_id: int, parent_id: int) -> list[Any]:
        """Get all child accounts of a parent account."""
        pass

    @abstractmethod
    async def get_active(self, company_id: int) -> list[Any]:
        """Get all active accounts for a company."""
        pass
