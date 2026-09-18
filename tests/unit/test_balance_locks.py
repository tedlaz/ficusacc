"""Unit tests for balance confirmations and the lock on earlier movements."""

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.infrastructure.database.models import (
    AccountModel,
    CompanyModel,
    TransactionLineModel,
    TransactionModel,
    UserModel,
)
from app.web import balance_locks


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_transaction(db, company_id, user_id, when, cash_id, other_id, amount, posted=True):
    transaction = TransactionModel(company_id=company_id, transaction_date=when, description="x",
                                   is_posted=posted, created_by_id=user_id)
    db.add(transaction)
    db.flush()
    db.add(TransactionLineModel(transaction_id=transaction.id, account_id=cash_id, amount=amount, line_order=0))
    db.add(TransactionLineModel(transaction_id=transaction.id, account_id=other_id, amount=-amount, line_order=1))
    db.commit()
    db.refresh(transaction)
    return transaction


@pytest.fixture
def book(db):
    company = CompanyModel(name="T", code="T")
    user = UserModel(email="u@x", hashed_password="h", full_name="U")
    db.add(company)
    db.add(user)
    db.flush()
    cash = AccountModel(company_id=company.id, code="38.00", name="Ταμείο", account_type="asset")
    other = AccountModel(company_id=company.id, code="64.00", name="Έξοδα", account_type="expense")
    db.add(cash)
    db.add(other)
    db.commit()
    add_transaction(db, company.id, user.id, date(2026, 1, 10), cash.id, other.id, Decimal("100"))
    add_transaction(db, company.id, user.id, date(2026, 1, 20), cash.id, other.id, Decimal("-30"))
    add_transaction(db, company.id, user.id, date(2026, 1, 15), cash.id, other.id, Decimal("500"), posted=False)
    add_transaction(db, company.id, user.id, date(2026, 2, 1), cash.id, other.id, Decimal("7"))
    return company, user, cash, other


def test_balance_as_of_counts_only_posted_lines_up_to_the_date(db, book):
    company, user, cash, other = book
    assert balance_locks.balance_as_of(db, cash.id, date(2026, 1, 9)) == Decimal("0.00")
    assert balance_locks.balance_as_of(db, cash.id, date(2026, 1, 10)) == Decimal("100.00")
    assert balance_locks.balance_as_of(db, cash.id, date(2026, 1, 31)) == Decimal("70.00")  # draft ignored
    assert balance_locks.balance_as_of(db, cash.id, date(2026, 12, 31)) == Decimal("77.00")
    assert balance_locks.balance_as_of(db, other.id, date(2026, 1, 31)) == Decimal("-70.00")


def test_confirm_rejects_a_wrong_figure_and_records_a_right_one(db, book):
    company, user, cash, other = book
    with pytest.raises(balance_locks.BalanceMismatch) as info:
        balance_locks.confirm(db, company.id, cash, date(2026, 1, 31), Decimal("75"), user.id)
    assert (info.value.computed, info.value.declared, info.value.difference) == (
        Decimal("70.00"), Decimal("75.00"), Decimal("5.00"))
    assert balance_locks.lock_date(db, cash.id) is None

    balance_locks.confirm(db, company.id, cash, date(2026, 1, 31), Decimal("70"), user.id)
    db.commit()
    assert balance_locks.lock_date(db, cash.id) == date(2026, 1, 31)
    assert balance_locks.lock_dates(db, company.id) == {cash.id: date(2026, 1, 31)}
    assert [c.as_of_date for c in balance_locks.confirmations(db, cash.id)] == [date(2026, 1, 31)]

    # Confirming the same date again just updates the row.
    balance_locks.confirm(db, company.id, cash, date(2026, 1, 31), Decimal("70.00"), user.id)
    db.commit()
    assert len(balance_locks.confirmations(db, cash.id)) == 1


def test_blocking_lines_uses_the_transaction_date_inclusive(db, book):
    company, user, cash, other = book
    balance_locks.confirm(db, company.id, cash, date(2026, 1, 20), Decimal("70"), user.id)
    db.commit()

    def blocked_for(when):
        transaction = add_transaction(db, company.id, user.id, when, cash.id, other.id, Decimal("1"), posted=False)
        return [(a.code, d) for a, d in balance_locks.blocking_lines(db, transaction)]

    assert blocked_for(date(2026, 1, 20)) == [("38.00", date(2026, 1, 20))]
    assert blocked_for(date(2026, 1, 1)) == [("38.00", date(2026, 1, 20))]
    assert blocked_for(date(2026, 1, 21)) == []
