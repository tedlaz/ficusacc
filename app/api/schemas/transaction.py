"""Transaction API schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class TransactionLineCreate(BaseModel):
    """Schema for creating a transaction line."""

    account_id: int
    amount: Decimal = Field(..., description="Positive for debit, negative for credit")
    description: str | None = None


class TransactionCreate(BaseModel):
    """Schema for creating a transaction."""

    transaction_date: date
    description: str = Field(..., min_length=1, max_length=500)
    reference: str | None = Field(None, max_length=100)
    lines: list[TransactionLineCreate] = Field(..., min_length=2)
    is_posted: bool = False

    @model_validator(mode="after")
    def validate_balance(self) -> "TransactionCreate":
        """Validate that debits equal credits."""
        total = sum(line.amount for line in self.lines)
        if total != Decimal("0"):
            raise ValueError(
                f"Transaction does not balance. Total: {total}. "
                "Debits (positive) must equal credits (negative)."
            )
        return self


class TransactionUpdate(BaseModel):
    """Schema for updating a transaction."""

    transaction_date: date | None = None
    description: str | None = Field(None, min_length=1, max_length=500)
    reference: str | None = None
    lines: list[TransactionLineCreate] | None = None

    @model_validator(mode="after")
    def validate_balance(self) -> "TransactionUpdate":
        """Validate that debits equal credits if lines are provided."""
        if self.lines:
            if len(self.lines) < 2:
                raise ValueError("Transaction must have at least 2 lines")
            total = sum(line.amount for line in self.lines)
            if total != Decimal("0"):
                raise ValueError(
                    f"Transaction does not balance. Total: {total}. "
                    "Debits (positive) must equal credits (negative)."
                )
        return self


class TransactionLineResponse(BaseModel):
    """Schema for transaction line response."""

    id: int
    transaction_id: int
    account_id: int
    amount: Decimal
    description: str | None
    line_order: int

    model_config = {"from_attributes": True}


class TransactionResponse(BaseModel):
    """Schema for transaction response."""

    id: int
    company_id: int
    transaction_date: date
    description: str
    reference: str | None
    is_posted: bool
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    lines: list[TransactionLineResponse]

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    """Schema for list of transactions response."""

    items: list[TransactionResponse]
    total: int
