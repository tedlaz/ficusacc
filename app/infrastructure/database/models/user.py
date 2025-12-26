"""User SQLModel database model."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .company import UserCompanyAccessModel
    from .transaction import TransactionModel


class UserModel(SQLModel, table=True):
    """SQLModel table for users."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    hashed_password: str = Field(max_length=255)
    full_name: str = Field(max_length=200)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    company_access: list["UserCompanyAccessModel"] = Relationship(back_populates="user")
    transactions: list["TransactionModel"] = Relationship(back_populates="created_by")

    class Config:
        """Pydantic config."""

        from_attributes = True
