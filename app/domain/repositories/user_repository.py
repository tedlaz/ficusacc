"""User repository interface."""

from abc import abstractmethod
from typing import Any

from app.domain.repositories.base import IRepository

# Type alias - actual type is UserModel
User = Any


class IUserRepository(IRepository[User]):
    """
    Repository interface for User entities.

    Users are not tenant-specific, so this extends IRepository
    rather than ITenantRepository.
    """

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address."""
        pass

    @abstractmethod
    async def get_active(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Get all active users."""
        pass

    @abstractmethod
    async def email_exists(self, email: str) -> bool:
        """Check if an email is already registered."""
        pass
