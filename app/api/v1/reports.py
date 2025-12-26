"""Reporting API routes."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.account import AccountResponse
from app.api.schemas.report import (
    AccountBalanceResponse,
    BalanceSheetResponse,
    GeneralLedgerResponse,
    IncomeStatementResponse,
    JournalDebitCreditResponse,
    JournalEntryResponse,
    JournalResponse,
    LedgerEntryResponse,
    TrialBalanceResponse,
)
from app.api.schemas.transaction import TransactionResponse
from app.application.services import ReportingService
from app.core.exceptions import EntityNotFoundError
from app.dependencies import CurrentCompany, CurrentUser, get_reporting_service

router = APIRouter()


def _convert_account_balance(balance) -> AccountBalanceResponse:
    """Convert AccountBalance to response schema."""
    return AccountBalanceResponse(
        account=AccountResponse.model_validate(balance.account),
        debit_total=balance.debit_total,
        credit_total=balance.credit_total,
        balance=balance.balance,
    )


@router.get("/balance-sheet", response_model=BalanceSheetResponse)
async def get_balance_sheet(
    as_of_date: date,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    reporting_service: Annotated[ReportingService, Depends(get_reporting_service)],
) -> BalanceSheetResponse:
    """
    Generate a balance sheet as of a specific date.

    Shows assets, liabilities, and equity with their balances.
    """
    report = await reporting_service.generate_balance_sheet(
        current_company.id,
        as_of_date,  # type: ignore
    )
    return BalanceSheetResponse(
        as_of_date=report.as_of_date,
        assets=[_convert_account_balance(b) for b in report.assets],
        liabilities=[_convert_account_balance(b) for b in report.liabilities],
        equity=[_convert_account_balance(b) for b in report.equity],
        total_assets=report.total_assets,
        total_liabilities=report.total_liabilities,
        total_equity=report.total_equity,
    )


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def get_trial_balance(
    as_of_date: date,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    reporting_service: Annotated[ReportingService, Depends(get_reporting_service)],
) -> TrialBalanceResponse:
    """
    Generate a trial balance as of a specific date.

    Shows all accounts with their debit and credit totals.
    Total debits should equal total credits.
    """
    report = await reporting_service.generate_trial_balance(
        current_company.id,
        as_of_date,  # type: ignore
    )
    return TrialBalanceResponse(
        as_of_date=report.as_of_date,
        accounts=[_convert_account_balance(b) for b in report.accounts],
        total_debits=report.total_debits,
        total_credits=report.total_credits,
    )


@router.get("/journal", response_model=JournalResponse)
async def get_journal(
    start_date: date,
    end_date: date,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    reporting_service: Annotated[ReportingService, Depends(get_reporting_service)],
) -> JournalResponse:
    """
    Generate a journal report for a date range.

    Shows all transactions with their debit and credit entries.
    """
    report = await reporting_service.generate_journal(
        current_company.id,
        start_date,
        end_date,  # type: ignore
    )

    entries = []
    for entry in report.entries:
        entries.append(
            JournalEntryResponse(
                transaction=TransactionResponse.model_validate(entry.transaction),
                debits=[
                    JournalDebitCreditResponse(
                        account=AccountResponse.model_validate(account),
                        amount=amount,
                    )
                    for account, amount in entry.debits
                ],
                credits=[
                    JournalDebitCreditResponse(
                        account=AccountResponse.model_validate(account),
                        amount=amount,
                    )
                    for account, amount in entry.credits
                ],
            )
        )

    entries.reverse()
    return JournalResponse(
        start_date=report.start_date,
        end_date=report.end_date,
        entries=entries,
    )


@router.get("/general-ledger/{account_id}", response_model=GeneralLedgerResponse)
async def get_general_ledger(
    account_id: int,
    start_date: date,
    end_date: date,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    reporting_service: Annotated[ReportingService, Depends(get_reporting_service)],
) -> GeneralLedgerResponse:
    """
    Generate a general ledger report for a specific account.

    Shows the opening balance, all transactions, and closing balance.
    """
    try:
        report = await reporting_service.generate_general_ledger(
            current_company.id,
            account_id,
            start_date,
            end_date,  # type: ignore
        )
        res = [
            LedgerEntryResponse(
                date=entry.date,
                description=entry.description,
                reference=entry.reference,
                debit=entry.debit,
                credit=entry.credit,
                balance=entry.balance,
            )
            for entry in report.entries
        ]
        res.reverse()
        return GeneralLedgerResponse(
            account=AccountResponse.model_validate(report.account),
            start_date=report.start_date,
            end_date=report.end_date,
            opening_balance=report.opening_balance,
            entries=res,
            closing_balance=report.closing_balance,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/income-statement", response_model=IncomeStatementResponse)
async def get_income_statement(
    start_date: date,
    end_date: date,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    reporting_service: Annotated[ReportingService, Depends(get_reporting_service)],
) -> IncomeStatementResponse:
    """
    Generate an income statement (P&L) for a date range.

    Shows revenues, expenses, and net income.
    """
    report = await reporting_service.generate_income_statement(
        current_company.id,
        start_date,
        end_date,  # type: ignore
    )
    return IncomeStatementResponse(
        start_date=report.start_date,
        end_date=report.end_date,
        revenues=[_convert_account_balance(b) for b in report.revenues],
        expenses=[_convert_account_balance(b) for b in report.expenses],
        total_revenue=report.total_revenue,
        total_expenses=report.total_expenses,
        net_income=report.net_income,
    )
