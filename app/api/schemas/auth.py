"""Authentication API schemas."""

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    password: str
    full_name: str
    company_name: str | None = None  # If provided, creates a new company


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str
    company_id: int | None = None


class TokenResponse(BaseModel):
    """Schema for token response."""

    access_token: str
    token_type: str = "bearer"
    user_id: int
    is_superuser: bool = False
    company_id: int | None = None
    company_name: str | None = None


class SwitchCompanyRequest(BaseModel):
    """Schema for switching company."""

    company_id: int
