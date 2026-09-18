"""Confirmed account balances: a reconciliation point that locks earlier movements."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class BalanceConfirmationModel(SQLModel, table=True):
    """The user vouched that ``account`` had ``balance`` at the end of ``as_of_date``.

    Posted movements dated on or before that day may no longer change (no posting, unposting or
    posted quick entries touching the account), so the confirmed figure stays true.
    """

    __tablename__ = "balance_confirmations"
    __table_args__ = (UniqueConstraint("account_id", "as_of_date", name="uq_confirmation_account_date"),)

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    as_of_date: date
    balance: Decimal = Field(decimal_places=2, max_digits=15)  # signed like the ledger: debit positive
    confirmed_by_id: int = Field(foreign_key="users.id")
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
