"""Account service for account management use cases."""

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.domain.repositories.account_repository import IAccountRepository
from app.domain.types import AccountType
from app.infrastructure.database.models.account import AccountModel as Account


class AccountService:
    """
    Service for account management operations.

    Follows Single Responsibility Principle by handling only account-related
    business logic. Depends on abstractions (IAccountRepository) following
    Dependency Inversion Principle.
    """

    def __init__(self, account_repo: IAccountRepository):
        self._repo = account_repo

    async def create_account(
        self,
        company_id: int,
        code: str,
        name: str,
        account_type: AccountType,
        parent_id: int | None = None,
        description: str | None = None,
    ) -> Account:
        """
        Create a new account.

        Args:
            company_id: The company this account belongs to
            code: Unique account code within the company
            name: Account name
            account_type: Type of account (asset, liability, equity, revenue, expense)
            parent_id: Optional parent account ID for hierarchical structure
            description: Optional account description

        Returns:
            The created account

        Raises:
            DuplicateEntityError: If account code already exists in company
            EntityNotFoundError: If parent account doesn't exist
        """
        # Check for duplicate code
        existing = await self._repo.get_by_code(company_id, code)
        if existing:
            raise DuplicateEntityError("Account", "code", code)

        # Validate parent exists if provided
        if parent_id:
            parent = await self._repo.get_by_id_for_tenant(parent_id, company_id)
            if not parent:
                raise EntityNotFoundError("Parent Account", parent_id)

        account = Account(
            company_id=company_id,
            code=code,
            name=name,
            account_type=account_type,
            parent_id=parent_id,
            description=description,
        )

        return await self._repo.create(account)

    async def get_account(self, company_id: int, account_id: int) -> Account:
        """
        Get an account by ID.

        Args:
            company_id: The company ID for tenant isolation
            account_id: The account ID

        Returns:
            The account

        Raises:
            EntityNotFoundError: If account not found
        """
        account = await self._repo.get_by_id_for_tenant(account_id, company_id)
        if not account:
            raise EntityNotFoundError("Account", account_id)
        return account

    async def get_accounts(self, company_id: int, skip: int = 0, limit: int = 100) -> list[Account]:
        """Get all accounts for a company."""
        return await self._repo.get_all_for_tenant(company_id, skip, limit)

    async def get_chart_of_accounts(self, company_id: int) -> list[Account]:
        """Get the complete chart of accounts for a company."""
        return await self._repo.get_all_for_tenant(company_id, skip=0, limit=10000)

    async def get_accounts_by_type(
        self, company_id: int, account_type: AccountType
    ) -> list[Account]:
        """Get all accounts of a specific type."""
        return await self._repo.get_by_type(company_id, account_type)

    async def get_active_accounts(self, company_id: int) -> list[Account]:
        """Get all active accounts for a company."""
        return await self._repo.get_active(company_id)

    async def update_account(
        self,
        company_id: int,
        account_id: int,
        code: str | None = None,
        name: str | None = None,
        account_type: AccountType | None = None,
        parent_id: int | None = None,
        is_active: bool | None = None,
        description: str | None = None,
    ) -> Account:
        """
        Update an existing account.

        Args:
            company_id: The company ID for tenant isolation
            account_id: The account ID to update
            code: New account code (optional)
            name: New account name (optional)
            account_type: New account type (optional)
            parent_id: New parent account ID (optional)
            is_active: New active status (optional)
            description: New description (optional)

        Returns:
            The updated account

        Raises:
            EntityNotFoundError: If account not found
            DuplicateEntityError: If new code already exists
        """
        account = await self._repo.get_by_id_for_tenant(account_id, company_id)
        if not account:
            raise EntityNotFoundError("Account", account_id)

        # Check for duplicate code if changing
        if code and code != account.code:
            existing = await self._repo.get_by_code(company_id, code)
            if existing:
                raise DuplicateEntityError("Account", "code", code)
            account.code = code

        if name is not None:
            account.name = name
        if account_type is not None:
            account.account_type = account_type
        if parent_id is not None:
            # Validate parent exists
            if parent_id != 0:  # 0 means remove parent
                parent = await self._repo.get_by_id_for_tenant(parent_id, company_id)
                if not parent:
                    raise EntityNotFoundError("Parent Account", parent_id)
            account.parent_id = parent_id if parent_id != 0 else None
        if is_active is not None:
            account.is_active = is_active
        if description is not None:
            account.description = description

        result = await self._repo.update(account_id, account)
        if not result:
            raise EntityNotFoundError("Account", account_id)
        return result

    async def delete_account(self, company_id: int, account_id: int) -> bool:
        """
        Delete an account.

        Args:
            company_id: The company ID for tenant isolation
            account_id: The account ID to delete

        Returns:
            True if deleted successfully

        Raises:
            EntityNotFoundError: If account not found
        """
        deleted = await self._repo.delete_for_tenant(account_id, company_id)
        if not deleted:
            raise EntityNotFoundError("Account", account_id)
        return True
