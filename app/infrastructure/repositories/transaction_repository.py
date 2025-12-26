"""SQLModel implementation of Transaction repository."""

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.repositories.transaction_repository import ITransactionRepository
from app.infrastructure.database.models.transaction import (
    TransactionLineModel,
    TransactionModel,
)

# Use models directly as type aliases
Transaction = TransactionModel
TransactionLine = TransactionLineModel


class SQLModelTransactionRepository(ITransactionRepository):
    """SQLModel-based implementation of the Transaction repository."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> TransactionModel | None:
        """Get a transaction by ID with lines."""
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .where(TransactionModel.id == id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[TransactionModel]:
        """Get all transactions with lines."""
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .order_by(TransactionModel.transaction_date.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: TransactionModel) -> TransactionModel:
        """Create a new transaction with lines."""
        # Create the transaction model
        model = TransactionModel(
            company_id=entity.company_id,
            transaction_date=entity.transaction_date,
            description=entity.description,
            reference=entity.reference,
            is_posted=entity.is_posted,
            created_by_id=entity.created_by_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()

        # Add lines
        for idx, line in enumerate(entity.lines):
            line_model = TransactionLineModel(
                transaction_id=model.id,
                account_id=line.account_id,
                amount=line.amount,
                description=line.description,
                line_order=idx,
            )
            self._session.add(line_model)

        await self._session.flush()

        # Reload with lines - return the instrumented model
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .where(TransactionModel.id == model.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update(self, id: int, entity: TransactionModel) -> TransactionModel | None:
        """Update an existing transaction and its lines."""
        # Store the new lines data BEFORE any database operations
        # (entity might be the same object as what we fetch due to SQLAlchemy identity map)
        new_lines_data = [
            {
                "account_id": line.account_id,
                "amount": line.amount,
                "description": line.description,
            }
            for line in entity.lines
        ]

        # Fetch the transaction with its lines
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .where(TransactionModel.id == id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        # Update header fields
        model.transaction_date = entity.transaction_date
        model.description = entity.description
        model.reference = entity.reference
        model.is_posted = entity.is_posted
        model.updated_at = datetime.now(timezone.utc)

        # Clear all existing lines from the relationship
        model.lines.clear()
        await self._session.flush()

        # Add new lines from saved data
        for idx, line_data in enumerate(new_lines_data):
            line_model = TransactionLineModel(
                transaction_id=id,
                account_id=line_data["account_id"],
                amount=line_data["amount"],
                description=line_data["description"],
                line_order=idx,
            )
            model.lines.append(line_model)

        await self._session.flush()

        # Reload with new lines
        await self._session.refresh(model, ["lines"])
        return model

    async def delete(self, id: int) -> bool:
        """Delete a transaction and its lines."""
        model = await self._session.get(TransactionModel, id)
        if not model:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    # Tenant-aware methods
    async def get_by_id_for_tenant(self, id: int, company_id: int) -> TransactionModel | None:
        """Get a transaction by ID for a specific company."""
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .where(TransactionModel.id == id, TransactionModel.company_id == company_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_tenant(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[TransactionModel]:
        """Get all transactions for a specific company."""
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .where(TransactionModel.company_id == company_id)
            .order_by(TransactionModel.transaction_date.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_tenant(self, id: int, company_id: int) -> bool:
        """Delete a transaction by ID for a specific company."""
        stmt = select(TransactionModel).where(
            TransactionModel.id == id, TransactionModel.company_id == company_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    # Transaction-specific methods
    async def get_with_lines(self, transaction_id: int, company_id: int) -> TransactionModel | None:
        """Get a transaction with all its lines loaded."""
        return await self.get_by_id_for_tenant(transaction_id, company_id)

    async def get_by_date_range(
        self, company_id: int, start_date: date, end_date: date
    ) -> list[TransactionModel]:
        """Get all transactions within a date range."""
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .where(
                TransactionModel.company_id == company_id,
                TransactionModel.transaction_date >= start_date,
                TransactionModel.transaction_date <= end_date,
            )
            .order_by(TransactionModel.transaction_date)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_account(
        self,
        company_id: int,
        account_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[TransactionModel]:
        """Get all transactions that include a specific account."""
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .join(TransactionLineModel)
            .where(
                TransactionModel.company_id == company_id,
                TransactionLineModel.account_id == account_id,
            )
        )

        if start_date:
            stmt = stmt.where(TransactionModel.transaction_date >= start_date)
        if end_date:
            stmt = stmt.where(TransactionModel.transaction_date <= end_date)

        stmt = stmt.order_by(TransactionModel.transaction_date).distinct()
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_posted(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[TransactionModel]:
        """Get all posted transactions for a company."""
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .where(
                TransactionModel.company_id == company_id,
                TransactionModel.is_posted,
            )
            .order_by(TransactionModel.transaction_date.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_unposted(
        self, company_id: int, skip: int = 0, limit: int = 100
    ) -> list[TransactionModel]:
        """Get all unposted (draft) transactions for a company."""
        stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.lines))
            .where(
                TransactionModel.company_id == company_id,
                TransactionModel.is_posted,
            )
            .order_by(TransactionModel.transaction_date.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
