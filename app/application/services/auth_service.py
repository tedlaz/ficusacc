"""Authentication service for login and token management."""

import re
import uuid

from app.core.exceptions import AuthenticationError, AuthorizationError, DuplicateEntityError
from app.core.security import create_access_token, hash_password, verify_password
from app.domain.repositories.company_repository import (
    ICompanyRepository,
    IUserCompanyAccessRepository,
)
from app.domain.repositories.user_repository import IUserRepository
from app.domain.types import UserRole
from app.infrastructure.database.models.company import (
    CompanyModel as Company,
)
from app.infrastructure.database.models.company import (
    UserCompanyAccessModel as UserCompanyAccess,
)
from app.infrastructure.database.models.user import UserModel as User


def _generate_company_code(name: str) -> str:
    """Generate a unique company code from name."""
    # Take first 3 chars of name (uppercase, alphanumeric only)
    base = re.sub(r"[^a-zA-Z0-9]", "", name.upper())[:3]
    if len(base) < 3:
        base = base.ljust(3, "X")
    # Add random suffix for uniqueness
    suffix = uuid.uuid4().hex[:5].upper()
    return f"{base}-{suffix}"


class AuthService:
    """
    Service for authentication and authorization operations.

    Handles login, token generation, and company access management.
    Supports multi-tenant authentication where users select their
    working company at login.
    """

    def __init__(
        self,
        user_repo: IUserRepository,
        company_repo: ICompanyRepository,
        access_repo: IUserCompanyAccessRepository,
    ):
        self._user_repo = user_repo
        self._company_repo = company_repo
        self._access_repo = access_repo

    async def register(
        self,
        email: str,
        password: str,
        full_name: str,
        company_name: str | None = None,
    ) -> tuple[str, User, Company | None]:
        """
        Register a new user and optionally create a company.

        Args:
            email: User's email
            password: User's password
            full_name: User's full name
            company_name: Optional company name to create

        Returns:
            Tuple of (access_token, user, company)

        Raises:
            DuplicateEntityError: If email already exists
        """
        # Check if email already exists
        existing = await self._user_repo.get_by_email(email)
        if existing:
            raise DuplicateEntityError("User", "email", email)

        # Check if this is the first user (will be superuser)
        user_count = await self._user_repo.count()
        is_first_user = user_count == 0

        # Create the user
        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
            is_superuser=is_first_user,
        )
        user = await self._user_repo.create(user)

        company: Company | None = None
        company_id: int | None = None

        # Create company if name provided
        if company_name:
            company_code = _generate_company_code(company_name)
            company = Company(name=company_name, code=company_code, is_active=True)
            company = await self._company_repo.create(company)
            company_id = company.id

            # Grant user admin access to the company
            access = UserCompanyAccess(
                user_id=user.id,  # type: ignore
                company_id=company.id,  # type: ignore
                role=UserRole.ADMIN,
                is_default=True,
            )
            await self._access_repo.create(access)

        token = create_access_token(user.id, company_id)  # type: ignore
        return token, user, company

    async def authenticate(self, email: str, password: str) -> User:
        """
        Authenticate a user by email and password.

        Args:
            email: User's email
            password: User's password

        Returns:
            The authenticated user

        Raises:
            AuthenticationError: If credentials are invalid
        """
        user = await self._user_repo.get_by_email(email)
        if not user:
            raise AuthenticationError("Invalid email or password")

        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("User account is inactive")

        return user

    async def login(
        self,
        email: str,
        password: str,
        company_id: int | None = None,
    ) -> tuple[str, User, Company | None]:
        """
        Login a user and generate access token.

        If company_id is not provided, uses the user's default company.

        Args:
            email: User's email
            password: User's password
            company_id: Optional company ID to login to

        Returns:
            Tuple of (access_token, user, company)

        Raises:
            AuthenticationError: If credentials are invalid
            AuthorizationError: If user doesn't have access to the company
        """
        user = await self.authenticate(email, password)

        company: Company | None = None
        selected_company_id: int | None = None

        if company_id:
            # Verify user has access to the specified company
            if not await self._access_repo.has_access(user.id, company_id):  # type: ignore
                raise AuthorizationError("No access to the specified company")
            company = await self._company_repo.get_by_id(company_id)
            if not company or not company.is_active:
                raise AuthorizationError("Company is not available")
            selected_company_id = company_id
        else:
            # Try to get user's default company
            default_access = await self._access_repo.get_default_company(user.id)  # type: ignore
            if default_access:
                company = await self._company_repo.get_by_id(default_access.company_id)
                if company and company.is_active:
                    selected_company_id = company.id

        token = create_access_token(user.id, selected_company_id)  # type: ignore
        return token, user, company

    async def get_user_companies(self, user_id: int) -> list[Company]:
        """
        Get all companies a user has access to.

        Args:
            user_id: The user ID

        Returns:
            List of companies the user can access
        """
        access_records = await self._access_repo.get_user_companies(user_id)
        companies = []
        for access in access_records:
            company = await self._company_repo.get_by_id(access.company_id)
            if company and company.is_active:
                companies.append(company)
        return companies

    async def switch_company(self, user_id: int, company_id: int) -> tuple[str, Company]:
        """
        Switch to a different company and generate new token.

        Args:
            user_id: The user ID
            company_id: The company ID to switch to

        Returns:
            Tuple of (new_access_token, company)

        Raises:
            AuthorizationError: If user doesn't have access to the company
        """
        if not await self._access_repo.has_access(user_id, company_id):
            raise AuthorizationError("No access to the specified company")

        company = await self._company_repo.get_by_id(company_id)
        if not company or not company.is_active:
            raise AuthorizationError("Company is not available")

        token = create_access_token(user_id, company_id)
        return token, company

    async def grant_company_access(
        self,
        user_id: int,
        company_id: int,
        role: str,
        is_default: bool = False,
    ) -> UserCompanyAccess:
        """
        Grant a user access to a company.

        Args:
            user_id: The user ID
            company_id: The company ID
            role: The role to assign
            is_default: Whether this is the user's default company

        Returns:
            The created access record
        """
        # Check if access already exists
        existing = await self._access_repo.get_user_company_access(user_id, company_id)
        if existing:
            # Update existing access
            existing.role = UserRole(role)
            existing.is_default = is_default
            result = await self._access_repo.update(existing.id, existing)  # type: ignore
            return result  # type: ignore

        # Create new access
        access = UserCompanyAccess(
            user_id=user_id,
            company_id=company_id,
            role=UserRole(role),
            is_default=is_default,
        )

        # If setting as default, unset other defaults
        if is_default:
            await self._access_repo.set_default_company(user_id, company_id)

        return await self._access_repo.create(access)

    async def revoke_company_access(self, user_id: int, company_id: int) -> bool:
        """
        Revoke a user's access to a company.

        Args:
            user_id: The user ID
            company_id: The company ID

        Returns:
            True if access was revoked
        """
        access = await self._access_repo.get_user_company_access(user_id, company_id)
        if not access:
            return False
        return await self._access_repo.delete(access.id)  # type: ignore

    async def set_default_company(self, user_id: int, company_id: int) -> bool:
        """
        Set a company as the user's default.

        Args:
            user_id: The user ID
            company_id: The company ID

        Returns:
            True if successful
        """
        return await self._access_repo.set_default_company(user_id, company_id)
