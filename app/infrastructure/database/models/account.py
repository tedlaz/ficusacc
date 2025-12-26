"""Account SQLModel database model."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from app.domain.types import AccountType

if TYPE_CHECKING:
    from .company import CompanyModel
    from .transaction import TransactionLineModel


class AccountBase(SQLModel):
    """Base account fields shared across create/update/response."""

    code: str = Field(max_length=20, index=True)
    name: str = Field(max_length=200)
    account_type: AccountType = Field(
        sa_type=sa.Enum(AccountType, values_callable=lambda x: [e.value for e in x])
    )
    parent_id: int | None = Field(default=None, foreign_key="accounts.id")
    is_active: bool = Field(default=True)
    description: str | None = Field(default=None, max_length=500)


class AccountModel(AccountBase, table=True):
    """SQLModel table for accounts - the single source of truth."""

    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    company: "CompanyModel" = Relationship(back_populates="accounts")
    parent: Optional["AccountModel"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "AccountModel.id"},
    )
    children: list["AccountModel"] = Relationship(back_populates="parent")
    transaction_lines: list["TransactionLineModel"] = Relationship(back_populates="account")

    class Config:
        """Pydantic config."""

        from_attributes = True
