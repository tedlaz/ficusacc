"""User management API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.user import (
    PasswordChange,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.application.services import UserService
from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.core.security import verify_password
from app.dependencies import CurrentUser, get_user_service

router = APIRouter()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Create a new user."""
    try:
        user = await user_service.create_user(
            email=data.email,
            password=data.password,
            full_name=data.full_name,
            is_superuser=data.is_superuser,
        )
        return UserResponse.model_validate(user)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser) -> UserResponse:
    """Get the current authenticated user's information."""
    return UserResponse.model_validate(current_user)


@router.get("/", response_model=UserListResponse)
async def list_users(
    current_user: CurrentUser,
    user_service: Annotated[UserService, Depends(get_user_service)],
    skip: int = 0,
    limit: int = 100,
) -> UserListResponse:
    """List all users. Requires authentication."""
    users = await user_service.get_users(skip, limit)
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=len(users),
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: CurrentUser,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Get a user by ID."""
    try:
        user = await user_service.get_user(user_id)
        return UserResponse.model_validate(user)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: CurrentUser,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Update a user."""
    # Only allow users to update themselves or superusers to update anyone
    if current_user.id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user",
        )

    try:
        user = await user_service.update_user(
            user_id=user_id,
            email=data.email,
            full_name=data.full_name,
            is_active=data.is_active,
            is_superuser=data.is_superuser if current_user.is_superuser else None,
        )
        return UserResponse.model_validate(user)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.post("/me/change-password", response_model=UserResponse)
async def change_password(
    data: PasswordChange,
    current_user: CurrentUser,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Change the current user's password."""
    # Verify current password
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    try:
        user = await user_service.change_password(
            user_id=current_user.id,  # type: ignore
            new_password=data.new_password,
        )
        return UserResponse.model_validate(user)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> None:
    """Delete a user. Only superusers can delete users."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can delete users",
        )

    try:
        await user_service.delete_user(user_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
