"""User service for user management use cases."""

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.core.security import hash_password
from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.database.models.user import UserModel as User


class UserService:
    """
    Service for user management operations.

    Handles user CRUD operations and password management.
    """

    def __init__(self, user_repo: IUserRepository):
        self._repo = user_repo

    async def create_user(
        self,
        email: str,
        password: str,
        full_name: str,
        is_superuser: bool = False,
    ) -> User:
        """
        Create a new user.

        Args:
            email: User's email address
            password: Plain text password (will be hashed)
            full_name: User's full name
            is_superuser: Whether user is a superuser

        Returns:
            The created user

        Raises:
            DuplicateEntityError: If email already exists
        """
        if await self._repo.email_exists(email):
            raise DuplicateEntityError("User", "email", email)

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_superuser=is_superuser,
        )

        return await self._repo.create(user)

    async def get_user(self, user_id: int) -> User:
        """
        Get a user by ID.

        Args:
            user_id: The user ID

        Returns:
            The user

        Raises:
            EntityNotFoundError: If user not found
        """
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise EntityNotFoundError("User", user_id)
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email address."""
        return await self._repo.get_by_email(email)

    async def get_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Get all users."""
        return await self._repo.get_all(skip, limit)

    async def get_active_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Get all active users."""
        return await self._repo.get_active(skip, limit)

    async def update_user(
        self,
        user_id: int,
        email: str | None = None,
        full_name: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
    ) -> User:
        """
        Update a user.

        Args:
            user_id: The user ID to update
            email: New email (optional)
            full_name: New full name (optional)
            is_active: New active status (optional)
            is_superuser: New superuser status (optional)

        Returns:
            The updated user

        Raises:
            EntityNotFoundError: If user not found
            DuplicateEntityError: If new email already exists
        """
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise EntityNotFoundError("User", user_id)

        # Check for duplicate email if changing
        if email and email != user.email:
            if await self._repo.email_exists(email):
                raise DuplicateEntityError("User", "email", email)
            user.email = email

        if full_name is not None:
            user.full_name = full_name
        if is_active is not None:
            user.is_active = is_active
        if is_superuser is not None:
            user.is_superuser = is_superuser

        result = await self._repo.update(user_id, user)
        if not result:
            raise EntityNotFoundError("User", user_id)
        return result

    async def change_password(self, user_id: int, new_password: str) -> User:
        """
        Change a user's password.

        Args:
            user_id: The user ID
            new_password: New plain text password

        Returns:
            The updated user

        Raises:
            EntityNotFoundError: If user not found
        """
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise EntityNotFoundError("User", user_id)

        user.hashed_password = hash_password(new_password)
        result = await self._repo.update(user_id, user)
        if not result:
            raise EntityNotFoundError("User", user_id)
        return result

    async def delete_user(self, user_id: int) -> bool:
        """
        Delete a user.

        Args:
            user_id: The user ID to delete

        Returns:
            True if deleted successfully

        Raises:
            EntityNotFoundError: If user not found
        """
        deleted = await self._repo.delete(user_id)
        if not deleted:
            raise EntityNotFoundError("User", user_id)
        return True
