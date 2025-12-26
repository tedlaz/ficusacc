"""Transaction service for transaction management use cases."""

from datetime import date
from decimal import Decimal

from app.core.exceptions import (
    EntityNotFoundError,
    InsufficientTransactionLinesError,
    TransactionNotBalancedError,
    ValidationError,
)
from app.domain.repositories.account_repository import IAccountRepository
from app.domain.repositories.transaction_repository import ITransactionRepository
from app.infrastructure.database.models.transaction import (
    TransactionLineModel as TransactionLine,
)
from app.infrastructure.database.models.transaction import (
    TransactionModel as Transaction,
)


class TransactionService:
    """
    Service for transaction management operations.

    Handles double-entry accounting validation rules:
    - Transactions must have at least 2 lines
    - Total debits must equal total credits (sum = 0)
    - Debits are positive amounts, credits are negative
    """

    def __init__(
        self,
        transaction_repo: ITransactionRepository,
        account_repo: IAccountRepository,
    ):
        self._txn_repo = transaction_repo
        self._account_repo = account_repo

    def _validate_transaction_lines(self, lines: list[TransactionLine]) -> None:
        """
        Validate transaction lines meet double-entry requirements.

        Args:
            lines: List of transaction lines

        Raises:
            InsufficientTransactionLinesError: If fewer than 2 lines
            TransactionNotBalancedError: If debits don't equal credits
        """
        if len(lines) < 2:
            raise InsufficientTransactionLinesError()

        total = sum(line.amount for line in lines)
        if total != Decimal("0"):
            raise TransactionNotBalancedError(str(total))

    async def _validate_accounts_exist(self, company_id: int, lines: list[TransactionLine]) -> None:
        """
        Validate all accounts in transaction lines exist and belong to company.

        Args:
            company_id: The company ID
            lines: List of transaction lines

        Raises:
            EntityNotFoundError: If any account doesn't exist
        """
        for line in lines:
            account = await self._account_repo.get_by_id_for_tenant(line.account_id, company_id)
            if not account:
                raise EntityNotFoundError("Account", line.account_id)
            if not account.is_active:
                raise ValidationError(f"Account {account.code} is inactive and cannot be used")

    async def create_transaction(
        self,
        company_id: int,
        user_id: int,
        transaction_date: date,
        description: str,
        lines: list[dict],
        reference: str | None = None,
        is_posted: bool = False,
    ) -> Transaction:
        """
        Create a new transaction with journal entries.

        Args:
            company_id: The company this transaction belongs to
            user_id: The user creating the transaction
            transaction_date: Date of the transaction
            description: Transaction description
            lines: List of line items with account_id and amount
            reference: Optional external reference number
            is_posted: Whether the transaction is posted (default: draft)

        Returns:
            The created transaction

        Raises:
            InsufficientTransactionLinesError: If fewer than 2 lines
            TransactionNotBalancedError: If debits don't equal credits
            EntityNotFoundError: If any account doesn't exist
        """
        # Convert dict lines to TransactionLine objects
        txn_lines = [
            TransactionLine(
                account_id=line["account_id"],
                amount=Decimal(str(line["amount"])),
                description=line.get("description"),
            )
            for line in lines
        ]

        # Validate
        self._validate_transaction_lines(txn_lines)
        await self._validate_accounts_exist(company_id, txn_lines)

        # Create transaction (validation happens in entity)
        transaction = Transaction(
            company_id=company_id,
            created_by_id=user_id,
            transaction_date=transaction_date,
            description=description,
            reference=reference,
            is_posted=is_posted,
            lines=txn_lines,
        )

        return await self._txn_repo.create(transaction)

    async def get_transaction(self, company_id: int, transaction_id: int) -> Transaction:
        """
        Get a transaction by ID with all lines.

        Args:
            company_id: The company ID for tenant isolation
            transaction_id: The transaction ID

        Returns:
            The transaction with lines

        Raises:
            EntityNotFoundError: If transaction not found
        """
        transaction = await self._txn_repo.get_with_lines(transaction_id, company_id)
        if not transaction:
            raise EntityNotFoundError("Transaction", transaction_id)
        return transaction

    async def get_transactions(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[Transaction]:
        """Get all transactions for a company."""
        return await self._txn_repo.get_all_for_tenant(company_id, skip, limit)

    async def get_transactions_by_date_range(
        self, company_id: int, start_date: date, end_date: date
    ) -> list[Transaction]:
        """Get transactions within a date range."""
        return await self._txn_repo.get_by_date_range(company_id, start_date, end_date)

    async def get_transactions_by_account(
        self,
        company_id: int,
        account_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Transaction]:
        """Get all transactions for a specific account."""
        return await self._txn_repo.get_by_account(company_id, account_id, start_date, end_date)

    async def get_posted_transactions(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[Transaction]:
        """Get all posted transactions."""
        return await self._txn_repo.get_posted(company_id, skip, limit)

    async def get_draft_transactions(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[Transaction]:
        """Get all draft (unposted) transactions."""
        return await self._txn_repo.get_unposted(company_id, skip, limit)

    async def update_transaction(
        self,
        company_id: int,
        transaction_id: int,
        transaction_date: date | None = None,
        description: str | None = None,
        reference: str | None = None,
        lines: list[dict] | None = None,
    ) -> Transaction:
        """
        Update a transaction.

        Note: Posted transactions cannot be updated.

        Args:
            company_id: The company ID for tenant isolation
            transaction_id: The transaction ID to update
            transaction_date: New date (optional)
            description: New description (optional)
            reference: New reference (optional)
            lines: New lines (optional, replaces all existing)

        Returns:
            The updated transaction

        Raises:
            EntityNotFoundError: If transaction not found
            ValidationError: If transaction is already posted
        """
        transaction = await self._txn_repo.get_with_lines(transaction_id, company_id)
        if not transaction:
            raise EntityNotFoundError("Transaction", transaction_id)

        if transaction.is_posted:
            raise ValidationError("Cannot update a posted transaction")

        if transaction_date is not None:
            transaction.transaction_date = transaction_date
        if description is not None:
            transaction.description = description
        if reference is not None:
            transaction.reference = reference

        if lines is not None:
            # Convert and validate new lines
            txn_lines = [
                TransactionLine(
                    account_id=line["account_id"],
                    amount=Decimal(str(line["amount"])),
                    description=line.get("description"),
                )
                for line in lines
            ]
            self._validate_transaction_lines(txn_lines)
            await self._validate_accounts_exist(company_id, txn_lines)
            transaction.lines = txn_lines

        result = await self._txn_repo.update(transaction_id, transaction)
        if not result:
            raise EntityNotFoundError("Transaction", transaction_id)
        return result

    async def post_transaction(self, company_id: int, transaction_id: int) -> Transaction:
        """
        Post a transaction (finalize it).

        Posted transactions cannot be edited or deleted.

        Args:
            company_id: The company ID for tenant isolation
            transaction_id: The transaction ID to post

        Returns:
            The posted transaction

        Raises:
            EntityNotFoundError: If transaction not found
            ValidationError: If transaction is already posted
        """
        transaction = await self._txn_repo.get_with_lines(transaction_id, company_id)
        if not transaction:
            raise EntityNotFoundError("Transaction", transaction_id)

        if transaction.is_posted:
            raise ValidationError("Transaction is already posted")

        transaction.is_posted = True
        result = await self._txn_repo.update(transaction_id, transaction)
        if not result:
            raise EntityNotFoundError("Transaction", transaction_id)
        return result

    async def unpost_transaction(self, company_id: int, transaction_id: int) -> Transaction:
        """
        Unpost a transaction (revert to draft).

        This allows the transaction to be edited or deleted again.

        Args:
            company_id: The company ID for tenant isolation
            transaction_id: The transaction ID to unpost

        Returns:
            The unposted transaction

        Raises:
            EntityNotFoundError: If transaction not found
            ValidationError: If transaction is not posted
        """
        transaction = await self._txn_repo.get_with_lines(transaction_id, company_id)
        if not transaction:
            raise EntityNotFoundError("Transaction", transaction_id)

        if not transaction.is_posted:
            raise ValidationError("Transaction is not posted")

        transaction.is_posted = False
        result = await self._txn_repo.update(transaction_id, transaction)
        if not result:
            raise EntityNotFoundError("Transaction", transaction_id)
        return result

    async def delete_transaction(self, company_id: int, transaction_id: int) -> bool:
        """
        Delete a transaction.

        Posted transactions cannot be deleted.

        Args:
            company_id: The company ID for tenant isolation
            transaction_id: The transaction ID to delete

        Returns:
            True if deleted successfully

        Raises:
            EntityNotFoundError: If transaction not found
            ValidationError: If transaction is posted
        """
        transaction = await self._txn_repo.get_with_lines(transaction_id, company_id)
        if not transaction:
            raise EntityNotFoundError("Transaction", transaction_id)

        if transaction.is_posted:
            raise ValidationError("Cannot delete a posted transaction")

        deleted = await self._txn_repo.delete_for_tenant(transaction_id, company_id)
        if not deleted:
            raise EntityNotFoundError("Transaction", transaction_id)
        return True
