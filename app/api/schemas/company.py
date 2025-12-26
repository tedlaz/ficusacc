"""Company API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.types import UserRole


class CompanyCreate(BaseModel):
    """Schema for creating a company."""

    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=20)
    fiscal_year_start_month: int = Field(1, ge=1, le=12)
    currency: str = Field("EUR", min_length=3, max_length=3)


class CompanyUpdate(BaseModel):
    """Schema for updating a company."""

    name: str | None = Field(None, min_length=1, max_length=200)
    code: str | None = Field(None, min_length=1, max_length=20)
    fiscal_year_start_month: int | None = Field(None, ge=1, le=12)
    currency: str | None = Field(None, min_length=3, max_length=3)
    is_active: bool | None = None


class CompanyResponse(BaseModel):
    """Schema for company response."""

    id: int
    name: str
    code: str
    fiscal_year_start_month: int
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    """Schema for list of companies response."""

    items: list[CompanyResponse]
    total: int


class UserCompanyAccessCreate(BaseModel):
    """Schema for granting company access."""

    user_id: int
    company_id: int
    role: UserRole = UserRole.VIEWER
    is_default: bool = False


class UserCompanyAccessResponse(BaseModel):
    """Schema for user company access response."""

    id: int
    user_id: int
    company_id: int
    role: UserRole
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}
