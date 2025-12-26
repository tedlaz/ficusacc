"""SQLModel implementations of Company and UserCompanyAccess repositories."""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.company_repository import (
    ICompanyRepository,
    IUserCompanyAccessRepository,
)
from app.domain.types import UserRole
from app.infrastructure.database.models.company import (
    CompanyModel,
    UserCompanyAccessModel,
)


class SQLModelCompanyRepository(ICompanyRepository):
    """SQLModel-based implementation of the Company repository."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> CompanyModel | None:
        """Get a company by ID."""
        return await self._session.get(CompanyModel, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[CompanyModel]:
        """Get all companies."""
        stmt = select(CompanyModel).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: CompanyModel) -> CompanyModel:
        """Create a new company."""
        model = CompanyModel(
            name=entity.name,
            code=entity.code,
            fiscal_year_start_month=entity.fiscal_year_start_month,
            currency=entity.currency,
            is_active=entity.is_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def update(self, id: int, entity: CompanyModel) -> CompanyModel | None:
        """Update an existing company."""
        model = await self._session.get(CompanyModel, id)
        if not model:
            return None

        model.name = entity.name
        model.code = entity.code
        model.fiscal_year_start_month = entity.fiscal_year_start_month
        model.currency = entity.currency
        model.is_active = entity.is_active
        model.updated_at = datetime.now(timezone.utc)

        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def delete(self, id: int) -> bool:
        """Delete a company by ID."""
        model = await self._session.get(CompanyModel, id)
        if not model:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    # Company-specific methods
    async def get_by_code(self, code: str) -> CompanyModel | None:
        """Get a company by code."""
        stmt = select(CompanyModel).where(CompanyModel.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active(self, skip: int = 0, limit: int = 100) -> list[CompanyModel]:
        """Get all active companies."""
        stmt = select(CompanyModel).where(CompanyModel.is_active).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def code_exists(self, code: str) -> bool:
        """Check if a company code already exists."""
        stmt = select(CompanyModel.id).where(CompanyModel.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None


class SQLModelUserCompanyAccessRepository(IUserCompanyAccessRepository):
    """SQLModel-based implementation of the UserCompanyAccess repository."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> UserCompanyAccessModel | None:
        """Get access record by ID."""
        return await self._session.get(UserCompanyAccessModel, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[UserCompanyAccessModel]:
        """Get all access records."""
        stmt = select(UserCompanyAccessModel).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: UserCompanyAccessModel) -> UserCompanyAccessModel:
        """Create a new access record."""
        model = UserCompanyAccessModel(
            user_id=entity.user_id,
            company_id=entity.company_id,
            role=entity.role,
            is_default=entity.is_default,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def update(
        self, id: int, entity: UserCompanyAccessModel
    ) -> UserCompanyAccessModel | None:
        """Update an existing access record."""
        model = await self._session.get(UserCompanyAccessModel, id)
        if not model:
            return None

        model.role = entity.role
        model.is_default = entity.is_default

        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def delete(self, id: int) -> bool:
        """Delete an access record by ID."""
        model = await self._session.get(UserCompanyAccessModel, id)
        if not model:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    # UserCompanyAccess-specific methods
    async def get_user_companies(self, user_id: int) -> list[UserCompanyAccessModel]:
        """Get all company access records for a user."""
        stmt = select(UserCompanyAccessModel).where(UserCompanyAccessModel.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_company_users(self, company_id: int) -> list[UserCompanyAccessModel]:
        """Get all user access records for a company."""
        stmt = select(UserCompanyAccessModel).where(UserCompanyAccessModel.company_id == company_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_company_access(
        self, user_id: int, company_id: int
    ) -> UserCompanyAccessModel | None:
        """Get the access record for a specific user-company pair."""
        stmt = select(UserCompanyAccessModel).where(
            UserCompanyAccessModel.user_id == user_id,
            UserCompanyAccessModel.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_company(self, user_id: int) -> UserCompanyAccessModel | None:
        """Get the user's default company access."""
        stmt = select(UserCompanyAccessModel).where(
            UserCompanyAccessModel.user_id == user_id,
            UserCompanyAccessModel.is_default,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_default_company(self, user_id: int, company_id: int) -> bool:
        """Set a company as the user's default."""
        # First, unset all defaults for this user
        stmt = (
            update(UserCompanyAccessModel)
            .where(UserCompanyAccessModel.user_id == user_id)
            .values(is_default=False)
        )
        await self._session.execute(stmt)

        # Then set the new default
        stmt = (
            update(UserCompanyAccessModel)
            .where(
                UserCompanyAccessModel.user_id == user_id,
                UserCompanyAccessModel.company_id == company_id,
            )
            .values(is_default=True)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0  # type: ignore

    async def has_access(self, user_id: int, company_id: int) -> bool:
        """Check if a user has access to a company."""
        stmt = select(UserCompanyAccessModel.id).where(
            UserCompanyAccessModel.user_id == user_id,
            UserCompanyAccessModel.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_role(self, user_id: int, company_id: int, role: UserRole) -> bool:
        """Check if a user has a specific role in a company."""
        stmt = select(UserCompanyAccessModel.id).where(
            UserCompanyAccessModel.user_id == user_id,
            UserCompanyAccessModel.company_id == company_id,
            UserCompanyAccessModel.role == role.value,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
