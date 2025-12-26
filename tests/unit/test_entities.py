"""Unit tests for domain entities."""

from decimal import Decimal

from app.domain.types import AccountType
from app.infrastructure.database.models.account import AccountModel as Account
from app.infrastructure.database.models.transaction import (
    TransactionLineModel as TransactionLine,
)
from app.infrastructure.database.models.transaction import (
    TransactionModel as Transaction,
)


class TestAccount:
    """Tests for Account entity."""

    def test_create_account(self):
        """Test creating a valid account."""
        account = Account(
            company_id=1,
            code="1000",
            name="Cash",
            account_type=AccountType.ASSET,
        )
        assert account.code == "1000"
        assert account.name == "Cash"
        assert account.account_type == AccountType.ASSET
        assert account.is_active is True

    def test_account_with_parent(self):
        """Test creating an account with a parent."""
        account = Account(
            company_id=1,
            code="1010",
            name="Petty Cash",
            account_type=AccountType.ASSET,
            parent_id=1,
        )
        assert account.parent_id == 1

    def test_account_with_empty_code(self):
        """Test that account can be created (validation is done at API layer)."""
        # SQLModel doesn't enforce min_length at model level,
        # validation is done at the API schema layer
        account = Account(
            company_id=1,
            code="",  # Empty code - allowed at model level
            name="Test",
            account_type=AccountType.ASSET,
        )
        assert account.code == ""


class TestTransactionLine:
    """Tests for TransactionLine entity."""

    def test_create_debit_line(self):
        """Test creating a debit line (positive amount)."""
        line = TransactionLine(
            account_id=1,
            amount=Decimal("100.00"),
        )
        assert line.amount == Decimal("100.00")

    def test_create_credit_line(self):
        """Test creating a credit line (negative amount)."""
        line = TransactionLine(
            account_id=1,
            amount=Decimal("-100.00"),
        )
        assert line.amount == Decimal("-100.00")


class TestTransaction:
    """Tests for Transaction entity."""

    def test_create_balanced_transaction(self):
        """Test creating a valid balanced transaction."""
        transaction = Transaction(
            company_id=1,
            transaction_date="2024-01-15",
            description="Test transaction",
            created_by_id=1,
            lines=[
                TransactionLine(account_id=1, amount=Decimal("100.00")),
                TransactionLine(account_id=2, amount=Decimal("-100.00")),
            ],
        )
        assert len(transaction.lines) == 2

    def test_transaction_with_single_line(self):
        """Test that transaction model allows single line (validation at service layer)."""
        # SQLModel doesn't enforce line count at model level,
        # validation is done at the service/API layer
        transaction = Transaction(
            company_id=1,
            transaction_date="2024-01-15",
            description="Test",
            created_by_id=1,
            lines=[
                TransactionLine(account_id=1, amount=Decimal("100.00")),
            ],
        )
        assert len(transaction.lines) == 1

    def test_transaction_unbalanced(self):
        """Test that unbalanced transactions are allowed at model level."""
        # SQLModel doesn't enforce balance at model level,
        # validation is done at the service/API layer
        transaction = Transaction(
            company_id=1,
            transaction_date="2024-01-15",
            description="Test",
            created_by_id=1,
            lines=[
                TransactionLine(account_id=1, amount=Decimal("100.00")),
                TransactionLine(account_id=2, amount=Decimal("-50.00")),
            ],
        )
        # Unbalanced but allowed at model level
        total = sum(line.amount for line in transaction.lines)
        assert total == Decimal("50.00")  # Not balanced

    def test_complex_balanced_transaction(self):
        """Test a transaction with multiple lines that balance."""
        transaction = Transaction(
            company_id=1,
            transaction_date="2024-01-15",
            description="Multi-line transaction",
            created_by_id=1,
            lines=[
                TransactionLine(account_id=1, amount=Decimal("100.00")),
                TransactionLine(account_id=2, amount=Decimal("50.00")),
                TransactionLine(account_id=3, amount=Decimal("-75.00")),
                TransactionLine(account_id=4, amount=Decimal("-75.00")),
            ],
        )
        assert len(transaction.lines) == 4
        assert sum(line.amount for line in transaction.lines) == Decimal("0")
