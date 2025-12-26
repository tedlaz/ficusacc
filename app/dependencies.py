"""FastAPI dependencies for dependency injection."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services import (
    AccountService,
    AuthService,
    CompanyService,
    ReportingService,
    TransactionService,
    UserService,
)
from app.core.security import decode_access_token
from app.infrastructure.database import get_async_session
from app.infrastructure.database.models.company import CompanyModel as Company
from app.infrastructure.database.models.user import UserModel as User
from app.infrastructure.repositories import (
    SQLModelAccountRepository,
    SQLModelCompanyRepository,
    SQLModelTransactionRepository,
    SQLModelUserCompanyAccessRepository,
    SQLModelUserRepository,
)

# API Key header for Bearer token authentication
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


# Database session dependency
async def get_db() -> AsyncSession:
    """Get database session."""
    async for session in get_async_session():
        yield session


# Repository dependencies
def get_account_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SQLModelAccountRepository:
    """Get account repository."""
    return SQLModelAccountRepository(session)


def get_transaction_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SQLModelTransactionRepository:
    """Get transaction repository."""
    return SQLModelTransactionRepository(session)


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SQLModelUserRepository:
    """Get user repository."""
    return SQLModelUserRepository(session)


def get_company_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SQLModelCompanyRepository:
    """Get company repository."""
    return SQLModelCompanyRepository(session)


def get_user_company_access_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SQLModelUserCompanyAccessRepository:
    """Get user company access repository."""
    return SQLModelUserCompanyAccessRepository(session)


# Service dependencies
def get_account_service(
    account_repo: Annotated[SQLModelAccountRepository, Depends(get_account_repository)],
) -> AccountService:
    """Get account service."""
    return AccountService(account_repo)


def get_transaction_service(
    transaction_repo: Annotated[SQLModelTransactionRepository, Depends(get_transaction_repository)],
    account_repo: Annotated[SQLModelAccountRepository, Depends(get_account_repository)],
) -> TransactionService:
    """Get transaction service."""
    return TransactionService(transaction_repo, account_repo)


def get_user_service(
    user_repo: Annotated[SQLModelUserRepository, Depends(get_user_repository)],
) -> UserService:
    """Get user service."""
    return UserService(user_repo)


def get_company_service(
    company_repo: Annotated[SQLModelCompanyRepository, Depends(get_company_repository)],
) -> CompanyService:
    """Get company service."""
    return CompanyService(company_repo)


def get_auth_service(
    user_repo: Annotated[SQLModelUserRepository, Depends(get_user_repository)],
    company_repo: Annotated[SQLModelCompanyRepository, Depends(get_company_repository)],
    access_repo: Annotated[
        SQLModelUserCompanyAccessRepository, Depends(get_user_company_access_repository)
    ],
) -> AuthService:
    """Get auth service."""
    return AuthService(user_repo, company_repo, access_repo)


def get_reporting_service(
    account_repo: Annotated[SQLModelAccountRepository, Depends(get_account_repository)],
    transaction_repo: Annotated[SQLModelTransactionRepository, Depends(get_transaction_repository)],
) -> ReportingService:
    """Get reporting service."""
    return ReportingService(account_repo, transaction_repo)


def _extract_token(authorization: str | None) -> str:
    """Extract Bearer token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Handle "Bearer <token>" format
    if authorization.startswith("Bearer "):
        return authorization[7:]

    # Also accept raw token
    return authorization


# Authentication dependencies
async def get_current_user(
    authorization: Annotated[str | None, Depends(api_key_header)],
    user_repo: Annotated[SQLModelUserRepository, Depends(get_user_repository)],
) -> User:
    """
    Get the current authenticated user from the JWT token.

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = _extract_token(authorization)

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = await user_repo.get_by_id(int(user_id))
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )

    return user


async def get_current_company(
    authorization: Annotated[str | None, Depends(api_key_header)],
    company_repo: Annotated[SQLModelCompanyRepository, Depends(get_company_repository)],
) -> Company:
    """
    Get the current company from the JWT token.

    Raises:
        HTTPException: If no company is selected or company not found
    """
    token = _extract_token(authorization)

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    company_id = payload.get("company_id")
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No company selected. Please login with a company or switch company.",
        )

    company = await company_repo.get_by_id(int(company_id))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    if not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company is inactive",
        )

    return company


async def get_optional_current_company(
    authorization: Annotated[str | None, Depends(api_key_header)],
    company_repo: Annotated[SQLModelCompanyRepository, Depends(get_company_repository)],
) -> Company | None:
    """
    Get the current company from the JWT token, or None if not selected.
    """
    if not authorization:
        return None

    token = _extract_token(authorization) if authorization else None
    if not token:
        return None

    payload = decode_access_token(token)
    if payload is None:
        return None

    company_id = payload.get("company_id")
    if company_id is None:
        return None

    return await company_repo.get_by_id(int(company_id))


# Type aliases for common dependencies
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentCompany = Annotated[Company, Depends(get_current_company)]
OptionalCompany = Annotated[Company | None, Depends(get_optional_current_company)]
