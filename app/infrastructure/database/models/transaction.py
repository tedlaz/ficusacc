"""Transaction and TransactionLine SQLModel database models."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .account import AccountModel
    from .company import CompanyModel
    from .user import UserModel


class TransactionModel(SQLModel, table=True):
    """SQLModel table for transaction headers."""

    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    transaction_date: date = Field(index=True)
    description: str = Field(max_length=500)
    reference: str | None = Field(default=None, max_length=100)
    is_posted: bool = Field(default=False, index=True)
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    company: "CompanyModel" = Relationship(back_populates="transactions")
    created_by: "UserModel" = Relationship(back_populates="transactions")
    lines: list["TransactionLineModel"] = Relationship(
        back_populates="transaction",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    class Config:
        """Pydantic config."""

        from_attributes = True


class TransactionLineModel(SQLModel, table=True):
    """SQLModel table for transaction lines (journal entries)."""

    __tablename__ = "transaction_lines"

    id: int | None = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transactions.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    amount: Decimal = Field(decimal_places=2, max_digits=15)
    description: str | None = Field(default=None, max_length=500)
    line_order: int = Field(default=0)

    # Relationships
    transaction: TransactionModel = Relationship(back_populates="lines")
    account: "AccountModel" = Relationship(back_populates="transaction_lines")

    class Config:
        """Pydantic config."""

        from_attributes = True
