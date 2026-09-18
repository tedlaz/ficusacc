"""Balance confirmations and the lock they impose on earlier posted movements.

Pure SQLModel (no Flask): the routes decide how to report a refusal, this module decides whether
something is refused. Sign convention is the ledger's: positive = debit.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlmodel import Session, col, func, select

from app.infrastructure.database.models import (
    AccountModel,
    BalanceConfirmationModel,
    TransactionLineModel,
    TransactionModel,
)

ZERO = Decimal("0.00")


class BalanceMismatch(Exception):
    """The declared balance is not what the posted movements add up to."""

    def __init__(self, computed: Decimal, declared: Decimal):
        self.computed, self.declared = computed, declared
        super().__init__(f"computed {computed} != declared {declared}")

    @property
    def difference(self) -> Decimal:
        return self.declared - self.computed


def balance_as_of(db: Session, account_id: int, as_of: date) -> Decimal:
    """Net of posted lines of the account dated on or before ``as_of``."""
    total = db.exec(
        select(func.coalesce(func.sum(TransactionLineModel.amount), 0))
        .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
        .where(
            TransactionLineModel.account_id == account_id,
            TransactionModel.is_posted == True,
            TransactionModel.transaction_date <= as_of,
        )
    ).one()
    return Decimal(str(total)).quantize(Decimal("0.01"))


def lock_dates(db: Session, company_id: int) -> dict[int, date]:
    """Account id -> latest confirmed date; movements up to that day are locked."""
    rows = db.exec(
        select(BalanceConfirmationModel.account_id, func.max(BalanceConfirmationModel.as_of_date))
        .where(BalanceConfirmationModel.company_id == company_id)
        .group_by(BalanceConfirmationModel.account_id)
    ).all()
    return {account_id: date.fromisoformat(str(when)) for account_id, when in rows}


def lock_date(db: Session, account_id: int) -> date | None:
    latest = db.exec(
        select(func.max(BalanceConfirmationModel.as_of_date)).where(
            BalanceConfirmationModel.account_id == account_id
        )
    ).one()
    return date.fromisoformat(str(latest)) if latest else None


def blocking_lines(db: Session, transaction: TransactionModel) -> list[tuple[AccountModel, date]]:
    """(account, lock date) for every line whose account is locked on the transaction's date."""
    locks = lock_dates(db, transaction.company_id)
    blocked = []
    for line in transaction.lines:
        locked_until = locks.get(line.account_id)
        if locked_until is not None and transaction.transaction_date <= locked_until:
            account = db.get(AccountModel, line.account_id)
            if account is not None and all(a.id != account.id for a, _ in blocked):
                blocked.append((account, locked_until))
    return blocked


def confirm(db: Session, company_id: int, account: AccountModel, as_of: date, declared: Decimal,
            user_id: int) -> BalanceConfirmationModel:
    """Record the confirmation, or raise BalanceMismatch when the books disagree with ``declared``."""
    computed = balance_as_of(db, account.id, as_of)
    declared = Decimal(declared).quantize(Decimal("0.01"))
    if computed != declared:
        raise BalanceMismatch(computed, declared)
    row = db.exec(
        select(BalanceConfirmationModel).where(
            BalanceConfirmationModel.account_id == account.id,
            BalanceConfirmationModel.as_of_date == as_of,
        )
    ).first()
    if row is None:
        row = BalanceConfirmationModel(company_id=company_id, account_id=account.id, as_of_date=as_of,
                                       balance=declared, confirmed_by_id=user_id)
    else:
        row.balance = declared
        row.confirmed_by_id = user_id
    db.add(row)
    return row


def confirmations(db: Session, account_id: int) -> list[BalanceConfirmationModel]:
    """Newest first."""
    return list(
        db.exec(
            select(BalanceConfirmationModel)
            .where(BalanceConfirmationModel.account_id == account_id)
            .order_by(col(BalanceConfirmationModel.as_of_date).desc())
        ).all()
    )
