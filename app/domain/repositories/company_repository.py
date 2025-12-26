"""Company and UserCompanyAccess repository interfaces."""

from abc import abstractmethod
from typing import Any

from app.domain.repositories.base import IRepository
from app.domain.types import UserRole


class ICompanyRepository(IRepository[Any]):
    """
    Repository interface for Company entities.

    Companies are top-level entities (tenants) and not scoped
    to any other entity.
    """

    @abstractmethod
    async def get_by_code(self, code: str) -> Any | None:
        """Get a company by its unique code."""
        pass

    @abstractmethod
    async def get_active(self, skip: int = 0, limit: int = 100) -> list[Any]:
        """Get all active companies."""
        pass

    @abstractmethod
    async def code_exists(self, code: str) -> bool:
        """Check if a company code already exists."""
        pass


class IUserCompanyAccessRepository(IRepository[Any]):
    """
    Repository interface for UserCompanyAccess entities.

    Manages the many-to-many relationship between users and companies.
    """

    @abstractmethod
    async def get_user_companies(self, user_id: int) -> list[Any]:
        """Get all company access records for a user."""
        pass

    @abstractmethod
    async def get_company_users(self, company_id: int) -> list[Any]:
        """Get all user access records for a company."""
        pass

    @abstractmethod
    async def get_user_company_access(self, user_id: int, company_id: int) -> Any | None:
        """Get the access record for a specific user-company pair."""
        pass

    @abstractmethod
    async def get_default_company(self, user_id: int) -> Any | None:
        """Get the user's default company access."""
        pass

    @abstractmethod
    async def set_default_company(self, user_id: int, company_id: int) -> bool:
        """Set a company as the user's default."""
        pass

    @abstractmethod
    async def has_access(self, user_id: int, company_id: int) -> bool:
        """Check if a user has access to a company."""
        pass

    @abstractmethod
    async def has_role(self, user_id: int, company_id: int, role: UserRole) -> bool:
        """Check if a user has a specific role in a company."""
        pass
