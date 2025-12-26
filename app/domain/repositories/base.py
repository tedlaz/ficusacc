"""Base repository interfaces following Interface Segregation Principle."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class IRepository(ABC, Generic[T]):
    """
    Base repository interface for basic CRUD operations.

    This follows the Interface Segregation Principle by providing
    only the essential operations that all repositories need.
    """

    @abstractmethod
    async def get_by_id(self, id: int) -> T | None:
        """Get an entity by its ID."""
        pass

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> list[T]:
        """Get all entities with pagination."""
        pass

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create a new entity."""
        pass

    @abstractmethod
    async def update(self, id: int, entity: T) -> T | None:
        """Update an existing entity."""
        pass

    @abstractmethod
    async def delete(self, id: int) -> bool:
        """Delete an entity by its ID."""
        pass


class ITenantRepository(IRepository[T], ABC):
    """
    Repository interface with tenant (company) isolation.

    Extends IRepository with tenant-aware operations to ensure
    data isolation in a multi-tenant environment.
    """

    @abstractmethod
    async def get_by_id_for_tenant(self, id: int, company_id: int) -> T | None:
        """Get an entity by ID, scoped to a specific tenant."""
        pass

    @abstractmethod
    async def get_all_for_tenant(self, company_id: int, skip: int = 0, limit: int = 100) -> list[T]:
        """Get all entities for a specific tenant with pagination."""
        pass

    @abstractmethod
    async def delete_for_tenant(self, id: int, company_id: int) -> bool:
        """Delete an entity by ID, scoped to a specific tenant."""
        pass
