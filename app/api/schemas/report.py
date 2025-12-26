"""Report API schemas."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.api.schemas.account import AccountResponse
from app.api.schemas.transaction import TransactionResponse


class AccountBalanceResponse(BaseModel):
    """Schema for account balance in reports."""

    account: AccountResponse
    debit_total: Decimal
    credit_total: Decimal
    balance: Decimal


class BalanceSheetResponse(BaseModel):
    """Schema for balance sheet report."""

    as_of_date: date
    assets: list[AccountBalanceResponse]
    liabilities: list[AccountBalanceResponse]
    equity: list[AccountBalanceResponse]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal


class TrialBalanceResponse(BaseModel):
    """Schema for trial balance report."""

    as_of_date: date
    accounts: list[AccountBalanceResponse]
    total_debits: Decimal
    total_credits: Decimal


class JournalDebitCreditResponse(BaseModel):
    """Schema for debit/credit in journal entry."""

    account: AccountResponse
    amount: Decimal


class JournalEntryResponse(BaseModel):
    """Schema for journal entry in journal report."""

    transaction: TransactionResponse
    debits: list[JournalDebitCreditResponse]
    credits: list[JournalDebitCreditResponse]


class JournalResponse(BaseModel):
    """Schema for journal report."""

    start_date: date
    end_date: date
    entries: list[JournalEntryResponse]


class LedgerEntryResponse(BaseModel):
    """Schema for general ledger entry."""

    date: date
    description: str
    reference: str | None
    debit: Decimal
    credit: Decimal
    balance: Decimal


class GeneralLedgerResponse(BaseModel):
    """Schema for general ledger report."""

    account: AccountResponse
    start_date: date
    end_date: date
    opening_balance: Decimal
    entries: list[LedgerEntryResponse]
    closing_balance: Decimal


class IncomeStatementResponse(BaseModel):
    """Schema for income statement report."""

    start_date: date
    end_date: date
    revenues: list[AccountBalanceResponse]
    expenses: list[AccountBalanceResponse]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal
