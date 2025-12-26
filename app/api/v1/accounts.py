"""Account management API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.account import (
    AccountBulkCreate,
    AccountBulkCreateResponse,
    AccountCreate,
    AccountListResponse,
    AccountResponse,
    AccountUpdate,
)
from app.application.services import AccountService
from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.dependencies import CurrentCompany, CurrentUser, get_account_service
from app.domain.types import AccountType

router = APIRouter()


@router.post("/", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    account_service: Annotated[AccountService, Depends(get_account_service)],
) -> AccountResponse:
    """Create a new account in the current company."""
    try:
        account = await account_service.create_account(
            company_id=current_company.id,  # type: ignore
            code=data.code,
            name=data.name,
            account_type=data.account_type,
            parent_id=data.parent_id,
            description=data.description,
        )
        return AccountResponse.model_validate(account)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/", response_model=AccountListResponse)
async def list_accounts(
    current_user: CurrentUser,
    current_company: CurrentCompany,
    account_service: Annotated[AccountService, Depends(get_account_service)],
    skip: int = 0,
    limit: int = 100,
    account_type: AccountType | None = None,
    active_only: bool = False,
) -> AccountListResponse:
    """
    List accounts for the current company.

    Filters:
    - account_type: Filter by account type
    - active_only: Only return active accounts
    """
    if account_type:
        accounts = await account_service.get_accounts_by_type(
            current_company.id,
            account_type,  # type: ignore
        )
    elif active_only:
        accounts = await account_service.get_active_accounts(current_company.id)  # type: ignore
    else:
        accounts = await account_service.get_accounts(
            current_company.id,
            skip,
            limit,  # type: ignore
        )

    return AccountListResponse(
        items=[AccountResponse.model_validate(a) for a in accounts],
        total=len(accounts),
    )


@router.get("/chart", response_model=AccountListResponse)
async def get_chart_of_accounts(
    current_user: CurrentUser,
    current_company: CurrentCompany,
    account_service: Annotated[AccountService, Depends(get_account_service)],
) -> AccountListResponse:
    """Get the complete chart of accounts for the current company."""
    accounts = await account_service.get_chart_of_accounts(current_company.id)  # type: ignore
    return AccountListResponse(
        items=[AccountResponse.model_validate(a) for a in accounts],
        total=len(accounts),
    )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    account_service: Annotated[AccountService, Depends(get_account_service)],
) -> AccountResponse:
    """Get an account by ID."""
    try:
        account = await account_service.get_account(
            current_company.id,
            account_id,  # type: ignore
        )
        return AccountResponse.model_validate(account)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    data: AccountUpdate,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    account_service: Annotated[AccountService, Depends(get_account_service)],
) -> AccountResponse:
    """Update an account."""
    try:
        account = await account_service.update_account(
            company_id=current_company.id,  # type: ignore
            account_id=account_id,
            code=data.code,
            name=data.name,
            account_type=data.account_type,
            parent_id=data.parent_id,
            is_active=data.is_active,
            description=data.description,
        )
        return AccountResponse.model_validate(account)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: int,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    account_service: Annotated[AccountService, Depends(get_account_service)],
) -> None:
    """Delete an account."""
    try:
        await account_service.delete_account(current_company.id, account_id)  # type: ignore
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.post("/bulk", response_model=AccountBulkCreateResponse)
async def bulk_create_accounts(
    data: AccountBulkCreate,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    account_service: Annotated[AccountService, Depends(get_account_service)],
) -> AccountBulkCreateResponse:
    """Bulk create accounts from a list (e.g., from CSV import)."""
    created = 0
    errors: list[str] = []

    for item in data.accounts:
        try:
            await account_service.create_account(
                company_id=current_company.id,  # type: ignore
                code=item.code,
                name=item.name,
                account_type=item.account_type,
            )
            created += 1
        except DuplicateEntityError:
            errors.append(f"Account code '{item.code}' already exists")
        except Exception as e:
            errors.append(f"Error creating account '{item.code}': {str(e)}")

    return AccountBulkCreateResponse(created=created, errors=errors)
