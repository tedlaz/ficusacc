"""SQLModel implementation of User repository."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.database.models.user import UserModel


class SQLModelUserRepository(IUserRepository):
    """SQLModel-based implementation of the User repository."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> UserModel | None:
        """Get a user by ID."""
        return await self._session.get(UserModel, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[UserModel]:
        """Get all users."""
        stmt = select(UserModel).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: UserModel) -> UserModel:
        """Create a new user."""
        model = UserModel(
            email=entity.email,
            hashed_password=entity.hashed_password,
            full_name=entity.full_name,
            is_active=entity.is_active,
            is_superuser=entity.is_superuser,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def update(self, id: int, entity: UserModel) -> UserModel | None:
        """Update an existing user."""
        model = await self._session.get(UserModel, id)
        if not model:
            return None

        model.email = entity.email
        model.full_name = entity.full_name
        model.is_active = entity.is_active
        model.is_superuser = entity.is_superuser
        model.updated_at = datetime.now(timezone.utc)

        # Only update password if provided
        if entity.hashed_password:
            model.hashed_password = entity.hashed_password

        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def delete(self, id: int) -> bool:
        """Delete a user by ID."""
        model = await self._session.get(UserModel, id)
        if not model:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    # User-specific methods
    async def get_by_email(self, email: str) -> UserModel | None:
        """Get a user by email."""
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active(self, skip: int = 0, limit: int = 100) -> list[UserModel]:
        """Get active users."""
        stmt = select(UserModel).where(UserModel.is_active == True).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def email_exists(self, email: str) -> bool:
        """Check if email is already registered."""
        user = await self.get_by_email(email)
        return user is not None

    async def count(self) -> int:
        """Get the total number of users."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(UserModel)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def email_exists(self, email: str) -> bool:
        """Check if an email is already registered."""
        stmt = select(UserModel.id).where(UserModel.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
