"""Company service for company management use cases."""

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.domain.repositories.company_repository import ICompanyRepository
from app.infrastructure.database.models.company import CompanyModel as Company


class CompanyService:
    """
    Service for company management operations.

    Companies are the tenants in the multi-tenant system.
    Each company has isolated data (accounts, transactions).
    """

    def __init__(self, company_repo: ICompanyRepository):
        self._repo = company_repo

    async def create_company(
        self,
        name: str,
        code: str,
        fiscal_year_start_month: int = 1,
        currency: str = "USD",
    ) -> Company:
        """
        Create a new company.

        Args:
            name: Company name
            code: Unique company code
            fiscal_year_start_month: Start month of fiscal year (1-12)
            currency: Three-letter currency code

        Returns:
            The created company

        Raises:
            DuplicateEntityError: If company code already exists
        """
        if await self._repo.code_exists(code):
            raise DuplicateEntityError("Company", "code", code)

        company = Company(
            name=name,
            code=code,
            fiscal_year_start_month=fiscal_year_start_month,
            currency=currency,
        )

        return await self._repo.create(company)

    async def get_company(self, company_id: int) -> Company:
        """
        Get a company by ID.

        Args:
            company_id: The company ID

        Returns:
            The company

        Raises:
            EntityNotFoundError: If company not found
        """
        company = await self._repo.get_by_id(company_id)
        if not company:
            raise EntityNotFoundError("Company", company_id)
        return company

    async def get_company_by_code(self, code: str) -> Company | None:
        """Get a company by its unique code."""
        return await self._repo.get_by_code(code)

    async def get_companies(self, skip: int = 0, limit: int = 100) -> list[Company]:
        """Get all companies."""
        return await self._repo.get_all(skip, limit)

    async def get_active_companies(self, skip: int = 0, limit: int = 100) -> list[Company]:
        """Get all active companies."""
        return await self._repo.get_active(skip, limit)

    async def update_company(
        self,
        company_id: int,
        name: str | None = None,
        code: str | None = None,
        fiscal_year_start_month: int | None = None,
        currency: str | None = None,
        is_active: bool | None = None,
    ) -> Company:
        """
        Update a company.

        Args:
            company_id: The company ID to update
            name: New name (optional)
            code: New code (optional)
            fiscal_year_start_month: New fiscal year start month (optional)
            currency: New currency (optional)
            is_active: New active status (optional)

        Returns:
            The updated company

        Raises:
            EntityNotFoundError: If company not found
            DuplicateEntityError: If new code already exists
        """
        company = await self._repo.get_by_id(company_id)
        if not company:
            raise EntityNotFoundError("Company", company_id)

        # Check for duplicate code if changing
        if code and code != company.code:
            if await self._repo.code_exists(code):
                raise DuplicateEntityError("Company", "code", code)
            company.code = code

        if name is not None:
            company.name = name
        if fiscal_year_start_month is not None:
            company.fiscal_year_start_month = fiscal_year_start_month
        if currency is not None:
            company.currency = currency
        if is_active is not None:
            company.is_active = is_active

        result = await self._repo.update(company_id, company)
        if not result:
            raise EntityNotFoundError("Company", company_id)
        return result

    async def delete_company(self, company_id: int) -> bool:
        """
        Delete a company.

        Note: This will fail if there are related accounts or transactions.

        Args:
            company_id: The company ID to delete

        Returns:
            True if deleted successfully

        Raises:
            EntityNotFoundError: If company not found
        """
        deleted = await self._repo.delete(company_id)
        if not deleted:
            raise EntityNotFoundError("Company", company_id)
        return True
