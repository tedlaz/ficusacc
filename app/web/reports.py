"""Synchronous report calculations preserving the original accounting semantics."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import selectinload
from sqlmodel import Session, func, select

from app.domain.types import AccountType
from app.infrastructure.database.models import AccountModel, TransactionModel


@dataclass
class AccountBalance:
    account: AccountModel
    debit_total: Decimal = Decimal("0")
    credit_total: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")
    is_summary: bool = False
    level: int = 0


@dataclass
class SummaryAccount:
    """Display-only account generated from a dotted account-code prefix."""

    id: None
    code: str
    name: str
    account_type: AccountType


def transactions_between(db: Session, company_id: int, start: date, end: date):
    statement = (
        select(TransactionModel)
        .where(
            TransactionModel.company_id == company_id,
            TransactionModel.transaction_date >= start,
            TransactionModel.transaction_date <= end,
        )
        .options(selectinload(TransactionModel.lines))
        .order_by(TransactionModel.transaction_date)
    )
    return list(db.exec(statement).all())


def account_balances(db: Session, company_id: int, as_of: date, types=None):
    accounts = list(
        db.exec(
            select(AccountModel)
            .where(AccountModel.company_id == company_id)
            .order_by(AccountModel.code)
        ).all()
    )
    if types:
        accounts = [account for account in accounts if account.account_type in types]
    balances = {account.id: AccountBalance(account) for account in accounts}
    for transaction in transactions_between(db, company_id, date(1900, 1, 1), as_of):
        if not transaction.is_posted:
            continue
        for line in transaction.lines:
            item = balances.get(line.account_id)
            if item is None:
                continue
            if line.amount > 0:
                item.debit_total += line.amount
            else:
                item.credit_total += abs(line.amount)
    for item in balances.values():
        item.balance = item.debit_total - item.credit_total
    return balances


def trial_balance(db: Session, company_id: int, as_of: date, include_summaries: bool = False):
    accounts = [item for item in account_balances(db, company_id, as_of).values() if item.balance]
    total_debits = sum((item.debit_total for item in accounts), Decimal("0"))
    total_credits = sum((item.credit_total for item in accounts), Decimal("0"))

    if include_summaries:
        account_by_code = {item.account.code: item.account for item in accounts}
        parent_codes = set()
        grouped = {}
        for item in accounts:
            parts = item.account.code.split(".")
            codes = [item.account.code]
            for length in range(1, len(parts)):
                prefix = ".".join(parts[:length])
                parent_codes.add(prefix)
                codes.append(prefix)
            for code in codes:
                aggregate = grouped.setdefault(
                    code,
                    {
                        "debit": Decimal("0"),
                        "credit": Decimal("0"),
                        "balance": Decimal("0"),
                        "account_type": item.account.account_type,
                    },
                )
                aggregate["debit"] += item.debit_total
                aggregate["credit"] += item.credit_total
                aggregate["balance"] += item.balance

        rows = []
        for code in sorted(grouped):
            aggregate = grouped[code]
            account = account_by_code.get(code) or SummaryAccount(
                id=None,
                code=code,
                name=f"Σύνολο {code}",
                account_type=aggregate["account_type"],
            )
            rows.append(
                AccountBalance(
                    account=account,
                    debit_total=aggregate["debit"],
                    credit_total=aggregate["credit"],
                    balance=aggregate["balance"],
                    is_summary=code in parent_codes,
                    level=code.count("."),
                )
            )
        accounts = rows

    return {
        "as_of_date": as_of,
        "accounts": accounts,
        "total_debits": total_debits,
        "total_credits": total_credits,
    }


def balance_sheet(db: Session, company_id: int, as_of: date):
    balances = account_balances(
        db, company_id, as_of, [AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY]
    ).values()
    assets = [item for item in balances if item.account.account_type == AccountType.ASSET]
    liabilities = [item for item in balances if item.account.account_type == AccountType.LIABILITY]
    equity = [item for item in balances if item.account.account_type == AccountType.EQUITY]
    return {
        "as_of_date": as_of,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": sum((item.balance for item in assets), Decimal("0")),
        "total_liabilities": sum((abs(item.balance) for item in liabilities), Decimal("0")),
        "total_equity": sum((abs(item.balance) for item in equity), Decimal("0")),
    }


def income_statement(db: Session, company_id: int, start: date, end: date):
    accounts = list(
        db.exec(
            select(AccountModel)
            .where(AccountModel.company_id == company_id)
            .order_by(AccountModel.code)
        ).all()
    )
    accounts = [a for a in accounts if a.account_type in {AccountType.REVENUE, AccountType.EXPENSE}]
    balances = {a.id: AccountBalance(a) for a in accounts}
    for transaction in transactions_between(db, company_id, start, end):
        if not transaction.is_posted:
            continue
        for line in transaction.lines:
            item = balances.get(line.account_id)
            if item is None:
                continue
            if line.amount > 0:
                item.debit_total += line.amount
            else:
                item.credit_total += abs(line.amount)
    for item in balances.values():
        item.balance = item.debit_total - item.credit_total
    revenues = [x for x in balances.values() if x.account.account_type == AccountType.REVENUE]
    expenses = [x for x in balances.values() if x.account.account_type == AccountType.EXPENSE]
    revenue = sum((abs(x.balance) for x in revenues), Decimal("0"))
    expense = sum((x.balance for x in expenses), Decimal("0"))
    return {"start_date": start, "end_date": end, "revenues": revenues, "expenses": expenses,
            "total_revenue": revenue, "total_expenses": expense, "net_income": revenue - expense}


def journal(
    db: Session,
    company_id: int,
    start: date,
    end: date,
    requested_page: int | None = 1,
    page_size: int | None = None,
):
    filters = (
        TransactionModel.company_id == company_id,
        TransactionModel.transaction_date >= start,
        TransactionModel.transaction_date <= end,
    )
    total = db.exec(
        select(func.count()).select_from(TransactionModel).where(*filters)
    ).one()
    page = max(requested_page or 1, 1)
    pages = max((total + page_size - 1) // page_size, 1) if page_size else 1
    page = min(page, pages)
    statement = (
        select(TransactionModel)
        .where(*filters)
        .options(selectinload(TransactionModel.lines))
        .order_by(TransactionModel.transaction_date.desc(), TransactionModel.id.desc())
    )
    if page_size:
        statement = statement.offset((page - 1) * page_size).limit(page_size)

    accounts = {a.id: a for a in db.exec(select(AccountModel).where(AccountModel.company_id == company_id))}
    entries = []
    for transaction in db.exec(statement).all():
        debits, credits = [], []
        for line in transaction.lines:
            account = accounts.get(line.account_id)
            if account and line.amount > 0:
                debits.append((account, line.amount))
            elif account:
                credits.append((account, abs(line.amount)))
        entries.append({"transaction": transaction, "debits": debits, "credits": credits})
    return {
        "start_date": start,
        "end_date": end,
        "entries": entries,
        "pagination": {"page": page, "pages": pages, "total": total},
    }
