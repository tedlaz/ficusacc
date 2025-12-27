"""Reporting service for generating financial reports."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.domain.repositories.account_repository import IAccountRepository
from app.domain.repositories.transaction_repository import ITransactionRepository
from app.domain.types import AccountType
from app.infrastructure.database.models.account import AccountModel as Account
from app.infrastructure.database.models.transaction import TransactionModel as Transaction


@dataclass
class AccountBalance:
    """Account with its calculated balance."""

    account: Account
    debit_total: Decimal
    credit_total: Decimal
    balance: Decimal  # Debit - Credit (positive for debit balance)


@dataclass
class BalanceSheetReport:
    """Balance sheet report data."""

    as_of_date: date
    assets: list[AccountBalance]
    liabilities: list[AccountBalance]
    equity: list[AccountBalance]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal


@dataclass
class TrialBalanceReport:
    """Trial balance report data."""

    as_of_date: date
    accounts: list[AccountBalance]
    total_debits: Decimal
    total_credits: Decimal


@dataclass
class JournalEntry:
    """A single journal entry for the journal report."""

    transaction: Transaction
    debits: list[tuple[Account, Decimal]]  # Account, Amount
    credits: list[tuple[Account, Decimal]]  # Account, Amount (absolute value)


@dataclass
class JournalReport:
    """Journal report data."""

    start_date: date
    end_date: date
    entries: list[JournalEntry]


@dataclass
class LedgerEntry:
    """A single entry in the general ledger."""

    date: date
    description: str
    reference: str | None
    debit: Decimal
    credit: Decimal
    balance: Decimal


@dataclass
class GeneralLedgerReport:
    """General ledger report for a single account."""

    account: Account
    start_date: date
    end_date: date
    opening_balance: Decimal
    entries: list[LedgerEntry]
    closing_balance: Decimal


@dataclass
class IncomeStatementReport:
    """Income statement (P&L) report data."""

    start_date: date
    end_date: date
    revenues: list[AccountBalance]
    expenses: list[AccountBalance]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


class ReportingService:
    """
    Service for generating financial reports.

    Generates standard accounting reports:
    - Balance Sheet
    - Trial Balance
    - Journal
    - General Ledger
    - Income Statement
    """

    def __init__(
        self,
        account_repo: IAccountRepository,
        transaction_repo: ITransactionRepository,
    ):
        self._account_repo = account_repo
        self._txn_repo = transaction_repo

    async def _calculate_account_balances(
        self,
        company_id: int,
        as_of_date: date,
        account_types: list[AccountType] | None = None,
    ) -> dict[int, AccountBalance]:
        """
        Calculate balances for all accounts up to a given date.

        Args:
            company_id: The company ID
            as_of_date: Calculate balances up to this date
            account_types: Optional filter by account types

        Returns:
            Dictionary mapping account_id to AccountBalance
        """
        # Get all accounts
        accounts = await self._account_repo.get_all_for_tenant(company_id, skip=0, limit=10000)

        if account_types:
            accounts = [a for a in accounts if a.account_type in account_types]

        # Get all transactions up to as_of_date
        # Using a very early start date
        transactions = await self._txn_repo.get_by_date_range(
            company_id, date(1900, 1, 1), as_of_date
        )

        # Only count posted transactions
        transactions = [t for t in transactions if t.is_posted]

        # Calculate balances
        balances: dict[int, AccountBalance] = {}

        for account in accounts:
            balances[account.id] = AccountBalance(  # type: ignore
                account=account,
                debit_total=Decimal("0"),
                credit_total=Decimal("0"),
                balance=Decimal("0"),
            )

        for txn in transactions:
            for line in txn.lines:
                if line.account_id in balances:
                    if line.amount > 0:  # Debit
                        balances[line.account_id].debit_total += line.amount
                    else:  # Credit
                        balances[line.account_id].credit_total += abs(line.amount)

        # Calculate net balance for each account
        for balance in balances.values():
            balance.balance = balance.debit_total - balance.credit_total

        return balances

    async def generate_balance_sheet(self, company_id: int, as_of_date: date) -> BalanceSheetReport:
        """
        Generate a balance sheet as of a specific date.

        Args:
            company_id: The company ID
            as_of_date: Date for the balance sheet

        Returns:
            Balance sheet report
        """
        balances = await self._calculate_account_balances(
            company_id,
            as_of_date,
            [AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY],
        )

        assets = [b for b in balances.values() if b.account.account_type == AccountType.ASSET]
        liabilities = [
            b for b in balances.values() if b.account.account_type == AccountType.LIABILITY
        ]
        equity = [b for b in balances.values() if b.account.account_type == AccountType.EQUITY]

        # Sort by account code
        assets.sort(key=lambda x: x.account.code)
        liabilities.sort(key=lambda x: x.account.code)
        equity.sort(key=lambda x: x.account.code)

        total_assets = sum(b.balance for b in assets)
        total_liabilities = sum(
            abs(b.balance) for b in liabilities
        )  # Liabilities are credit balance
        total_equity = sum(abs(b.balance) for b in equity)  # Equity is credit balance

        return BalanceSheetReport(
            as_of_date=as_of_date,
            assets=assets,
            liabilities=liabilities,
            equity=equity,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            total_equity=total_equity,
        )

    async def generate_trial_balance(self, company_id: int, as_of_date: date) -> TrialBalanceReport:
        """
        Generate a trial balance as of a specific date.

        Args:
            company_id: The company ID
            as_of_date: Date for the trial balance

        Returns:
            Trial balance report
        """
        balances = await self._calculate_account_balances(company_id, as_of_date)

        # Filter out zero balances
        account_balances = [b for b in balances.values() if b.balance != 0]
        account_balances.sort(key=lambda x: x.account.code)

        total_debits = sum(b.debit_total for b in account_balances)
        total_credits = sum(b.credit_total for b in account_balances)

        return TrialBalanceReport(
            as_of_date=as_of_date,
            accounts=account_balances,
            total_debits=total_debits,
            total_credits=total_credits,
        )

    async def generate_journal(
        self, company_id: int, start_date: date, end_date: date
    ) -> JournalReport:
        """
        Generate a journal report for a date range.

        Args:
            company_id: The company ID
            start_date: Start of the period
            end_date: End of the period

        Returns:
            Journal report
        """
        transactions = await self._txn_repo.get_by_date_range(company_id, start_date, end_date)

        # Get all accounts for lookup
        accounts = await self._account_repo.get_all_for_tenant(company_id, skip=0, limit=10000)
        account_map = {a.id: a for a in accounts}

        entries = []
        for txn in transactions:
            debits = []
            credits = []
            for line in txn.lines:
                account = account_map.get(line.account_id)
                if account:
                    if line.amount > 0:
                        debits.append((account, line.amount))
                    else:
                        credits.append((account, abs(line.amount)))

            entries.append(
                JournalEntry(
                    transaction=txn,
                    debits=debits,
                    credits=credits,
                )
            )

        return JournalReport(
            start_date=start_date,
            end_date=end_date,
            entries=entries,
        )

    async def generate_general_ledger(
        self,
        company_id: int,
        account_id: int,
        start_date: date,
        end_date: date,
    ) -> GeneralLedgerReport:
        """
        Generate a general ledger report for a specific account.

        Args:
            company_id: The company ID
            account_id: The account ID
            start_date: Start of the period
            end_date: End of the period

        Returns:
            General ledger report
        """
        from app.core.exceptions import EntityNotFoundError

        account = await self._account_repo.get_by_id_for_tenant(account_id, company_id)
        if not account:
            raise EntityNotFoundError("Account", account_id)

        # Calculate opening balance (all transactions before start_date)
        opening_balances = await self._calculate_account_balances(
            company_id, start_date - timedelta(days=1)
        )
        opening_balance = opening_balances.get(account_id)
        opening = opening_balance.balance if opening_balance else Decimal("0")

        # Get transactions in the period
        transactions = await self._txn_repo.get_by_account(
            company_id, account_id, start_date, end_date
        )

        # Build ledger entries with running balance
        entries = []
        running_balance = opening

        for txn in sorted(transactions, key=lambda t: t.transaction_date):
            if not txn.is_posted:
                continue

            for line in txn.lines:
                if line.account_id == account_id:
                    debit = line.amount if line.amount > 0 else Decimal("0")
                    credit = abs(line.amount) if line.amount < 0 else Decimal("0")
                    running_balance += line.amount

                    entries.append(
                        LedgerEntry(
                            date=txn.transaction_date,
                            description=txn.description,
                            reference=txn.reference,
                            debit=debit,
                            credit=credit,
                            balance=running_balance,
                        )
                    )

        return GeneralLedgerReport(
            account=account,
            start_date=start_date,
            end_date=end_date,
            opening_balance=opening,
            entries=entries,
            closing_balance=running_balance,
        )

    async def generate_income_statement(
        self, company_id: int, start_date: date, end_date: date
    ) -> IncomeStatementReport:
        """
        Generate an income statement for a date range.

        Args:
            company_id: The company ID
            start_date: Start of the period
            end_date: End of the period

        Returns:
            Income statement report
        """
        # For income statement, we need transactions in the period only
        accounts = await self._account_repo.get_all_for_tenant(company_id, skip=0, limit=10000)

        revenue_accounts = [a for a in accounts if a.account_type == AccountType.REVENUE]
        expense_accounts = [a for a in accounts if a.account_type == AccountType.EXPENSE]

        transactions = await self._txn_repo.get_by_date_range(company_id, start_date, end_date)
        transactions = [t for t in transactions if t.is_posted]

        # Calculate balances for the period
        balances: dict[int, AccountBalance] = {}

        for account in revenue_accounts + expense_accounts:
            balances[account.id] = AccountBalance(  # type: ignore
                account=account,
                debit_total=Decimal("0"),
                credit_total=Decimal("0"),
                balance=Decimal("0"),
            )

        for txn in transactions:
            for line in txn.lines:
                if line.account_id in balances:
                    if line.amount > 0:
                        balances[line.account_id].debit_total += line.amount
                    else:
                        balances[line.account_id].credit_total += abs(line.amount)

        for balance in balances.values():
            balance.balance = balance.debit_total - balance.credit_total

        revenues = [b for b in balances.values() if b.account.account_type == AccountType.REVENUE]
        expenses = [b for b in balances.values() if b.account.account_type == AccountType.EXPENSE]

        revenues.sort(key=lambda x: x.account.code)
        expenses.sort(key=lambda x: x.account.code)

        # Revenue is credit balance (negative in our system)
        total_revenue = sum(abs(b.balance) for b in revenues)
        # Expenses are debit balance (positive)
        total_expenses = sum(b.balance for b in expenses)
        net_income = total_revenue - total_expenses

        return IncomeStatementReport(
            start_date=start_date,
            end_date=end_date,
            revenues=revenues,
            expenses=expenses,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            net_income=net_income,
        )
