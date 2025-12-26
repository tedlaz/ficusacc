"""SQLModel implementation of Account repository."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.account_repository import IAccountRepository
from app.domain.types import AccountType
from app.infrastructure.database.models.account import AccountModel

# AccountModel is the single source of truth, aliased as Account
Account = AccountModel


class SQLModelAccountRepository(IAccountRepository):
    """SQLModel-based implementation of the Account repository."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> Account | None:
        """Get an account by ID (not tenant-scoped)."""
        return await self._session.get(AccountModel, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[Account]:
        """Get all accounts (not tenant-scoped)."""
        stmt = select(AccountModel).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: Account) -> Account:
        """Create a new account."""
        entity.id = None  # Ensure ID is not set
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def update(self, id: int, entity: Account) -> Account | None:
        """Update an existing account."""
        model = await self._session.get(AccountModel, id)
        if not model:
            return None

        model.code = entity.code
        model.name = entity.name
        model.account_type = entity.account_type
        model.parent_id = entity.parent_id
        model.is_active = entity.is_active
        model.description = entity.description
        model.updated_at = datetime.now(timezone.utc)

        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def delete(self, id: int) -> bool:
        """Delete an account by ID."""
        model = await self._session.get(AccountModel, id)
        if not model:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    # Tenant-aware methods
    async def get_by_id_for_tenant(self, id: int, company_id: int) -> Account | None:
        """Get an account by ID for a specific company."""
        stmt = select(AccountModel).where(
            AccountModel.id == id, AccountModel.company_id == company_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_tenant(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[Account]:
        """Get all accounts for a specific company."""
        stmt = (
            select(AccountModel)
            .where(AccountModel.company_id == company_id)
            .order_by(AccountModel.code)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_tenant(self, id: int, company_id: int) -> bool:
        """Delete an account by ID for a specific company."""
        stmt = select(AccountModel).where(
            AccountModel.id == id, AccountModel.company_id == company_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    # Account-specific methods
    async def get_by_code(self, company_id: int, code: str) -> Account | None:
        """Get an account by code within a company."""
        stmt = select(AccountModel).where(
            AccountModel.company_id == company_id, AccountModel.code == code
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_type(self, company_id: int, account_type: AccountType) -> list[Account]:
        """Get all accounts of a specific type."""
        stmt = select(AccountModel).where(
            AccountModel.company_id == company_id,
            AccountModel.account_type == account_type,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_children(self, company_id: int, parent_id: int) -> list[Account]:
        """Get all child accounts of a parent."""
        stmt = select(AccountModel).where(
            AccountModel.company_id == company_id, AccountModel.parent_id == parent_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active(self, company_id: int) -> list[Account]:
        """Get all active accounts for a company."""
        stmt = (
            select(AccountModel)
            .where(AccountModel.company_id == company_id, AccountModel.is_active == True)
            .order_by(AccountModel.code)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
