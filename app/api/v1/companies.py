"""Company management API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.company import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
    UserCompanyAccessCreate,
    UserCompanyAccessResponse,
)
from app.application.services import AuthService, CompanyService
from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.dependencies import CurrentUser, get_auth_service, get_company_service

router = APIRouter()


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: CompanyCreate,
    current_user: CurrentUser,
    company_service: Annotated[CompanyService, Depends(get_company_service)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> CompanyResponse:
    """
    Create a new company.

    The creating user is automatically granted owner access.
    """
    try:
        company = await company_service.create_company(
            name=data.name,
            code=data.code,
            fiscal_year_start_month=data.fiscal_year_start_month,
            currency=data.currency,
        )

        # Grant owner access to the creating user
        await auth_service.grant_company_access(
            user_id=current_user.id,  # type: ignore
            company_id=company.id,  # type: ignore
            role="owner",
            is_default=True,
        )

        return CompanyResponse.model_validate(company)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.get("/", response_model=CompanyListResponse)
async def list_companies(
    current_user: CurrentUser,
    company_service: Annotated[CompanyService, Depends(get_company_service)],
    skip: int = 0,
    limit: int = 100,
) -> CompanyListResponse:
    """
    List all companies.

    Superusers see all companies; regular users see only their accessible companies.
    """
    if current_user.is_superuser:
        companies = await company_service.get_companies(skip, limit)
    else:
        companies = await company_service.get_active_companies(skip, limit)

    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=len(companies),
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: int,
    current_user: CurrentUser,
    company_service: Annotated[CompanyService, Depends(get_company_service)],
) -> CompanyResponse:
    """Get a company by ID."""
    try:
        company = await company_service.get_company(company_id)
        return CompanyResponse.model_validate(company)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: int,
    data: CompanyUpdate,
    current_user: CurrentUser,
    company_service: Annotated[CompanyService, Depends(get_company_service)],
) -> CompanyResponse:
    """Update a company. Requires owner or admin access."""
    try:
        company = await company_service.update_company(
            company_id=company_id,
            name=data.name,
            code=data.code,
            fiscal_year_start_month=data.fiscal_year_start_month,
            currency=data.currency,
            is_active=data.is_active,
        )
        return CompanyResponse.model_validate(company)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: int,
    current_user: CurrentUser,
    company_service: Annotated[CompanyService, Depends(get_company_service)],
) -> None:
    """Delete a company. Only superusers can delete companies."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can delete companies",
        )

    try:
        await company_service.delete_company(company_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


# User access management
@router.post(
    "/{company_id}/access",
    response_model=UserCompanyAccessResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_access(
    company_id: int,
    data: UserCompanyAccessCreate,
    current_user: CurrentUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserCompanyAccessResponse:
    """Grant a user access to a company."""
    access = await auth_service.grant_company_access(
        user_id=data.user_id,
        company_id=company_id,
        role=data.role.value,
        is_default=data.is_default,
    )
    return UserCompanyAccessResponse.model_validate(access)


@router.delete("/{company_id}/access/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_access(
    company_id: int,
    user_id: int,
    current_user: CurrentUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Revoke a user's access to a company."""
    revoked = await auth_service.revoke_company_access(user_id, company_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access record not found",
        )
