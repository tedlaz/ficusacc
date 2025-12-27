"""Company and UserCompanyAccess SQLModel database models."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .account import AccountModel
    from .transaction import TransactionModel
    from .user import UserModel


class CompanyModel(SQLModel, table=True):
    """SQLModel table for companies (tenants)."""

    __tablename__ = "companies"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    code: str = Field(unique=True, index=True, max_length=20)
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)
    currency: str = Field(default="EUR", max_length=3)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    accounts: list["AccountModel"] = Relationship(back_populates="company")
    transactions: list["TransactionModel"] = Relationship(back_populates="company")
    user_access: list["UserCompanyAccessModel"] = Relationship(back_populates="company")

    class Config:
        """Pydantic config."""

        from_attributes = True


class UserCompanyAccessModel(SQLModel, table=True):
    """SQLModel table for user-company access (many-to-many with role)."""

    __tablename__ = "user_company_access"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    role: str = Field(default="viewer", max_length=20)  # Stored as string enum value
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    user: "UserModel" = Relationship(back_populates="company_access")
    company: "CompanyModel" = Relationship(back_populates="user_access")

    class Config:
        """Pydantic config."""

        from_attributes = True
