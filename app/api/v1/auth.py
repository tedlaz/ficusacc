"""Authentication API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.auth import LoginRequest, RegisterRequest, SwitchCompanyRequest, TokenResponse
from app.api.schemas.company import CompanyResponse
from app.application.services import AuthService
from app.core.exceptions import AuthenticationError, AuthorizationError, DuplicateEntityError
from app.dependencies import CurrentUser, get_auth_service

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """
    Register a new user.

    Optionally create a new company that the user will have admin access to.
    """
    try:
        token, user, company = await auth_service.register(
            email=data.email,
            password=data.password,
            full_name=data.full_name,
            company_name=data.company_name,
        )
        return TokenResponse(
            access_token=token,
            user_id=user.id,  # type: ignore
            company_id=company.id if company else None,
            company_name=company.name if company else None,
        )
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """
    Login with email and password.

    Optionally specify a company_id to login directly to that company.
    If not specified, uses the user's default company.
    """
    try:
        token, user, company = await auth_service.login(
            email=data.email,
            password=data.password,
            company_id=data.company_id,
        )
        return TokenResponse(
            access_token=token,
            user_id=user.id,  # type: ignore
            company_id=company.id if company else None,
            company_name=company.name if company else None,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)
    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)


@router.get("/companies", response_model=list[CompanyResponse])
async def list_user_companies(
    current_user: CurrentUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> list[CompanyResponse]:
    """List all companies the current user has access to."""
    companies = await auth_service.get_user_companies(current_user.id)  # type: ignore
    return [CompanyResponse.model_validate(c) for c in companies]


@router.post("/switch-company", response_model=TokenResponse)
async def switch_company(
    data: SwitchCompanyRequest,
    current_user: CurrentUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Switch to a different company and get a new token."""
    try:
        token, company = await auth_service.switch_company(
            user_id=current_user.id,  # type: ignore
            company_id=data.company_id,
        )
        return TokenResponse(
            access_token=token,
            user_id=current_user.id,  # type: ignore
            company_id=company.id,
            company_name=company.name,
        )
    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
