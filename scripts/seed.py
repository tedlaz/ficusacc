"""Database seeding script for development."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.core.security import hash_password
from app.domain.types import AccountType
from app.infrastructure.database import engine, get_async_session
from app.infrastructure.database.models import (
    AccountModel,
    CompanyModel,
    UserCompanyAccessModel,
    UserModel,
)


async def seed_database() -> None:
    """Seed the database with initial data."""
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Get a session
    async for session in get_async_session():
        await seed_data(session)
        break

    print("✅ Database seeded successfully!")


async def seed_data(session: AsyncSession) -> None:
    """Insert seed data."""
    # Create a test company
    company = CompanyModel(
        name="DEMO",
        code="DEMO",
        is_active=True,
    )
    session.add(company)
    await session.flush()
    print(f"  Created company: {company.name} (ID: {company.id})")

    # Create a test user
    user = UserModel(
        email="admin@demo.com",
        hashed_password=hash_password("adminpass"),
        full_name="Admin User",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    print(f"  Created user: {user.email} (ID: {user.id})")

    # Grant user access to company
    access = UserCompanyAccessModel(
        user_id=user.id,
        company_id=company.id,
        role="admin",
        is_default=True,
    )
    session.add(access)
    await session.flush()
    print(f"  Granted {user.email} admin access to {company.name}")

    # Create chart of accounts
    accounts = [
        # Assets
        AccountModel(
            company_id=company.id,
            code="38.00.00",
            name="Ταμείο",
            account_type=AccountType.ASSET.value,
        ),
        AccountModel(
            company_id=company.id,
            code="38.03.01",
            name="Εθνική Τράπεζα",
            account_type=AccountType.ASSET.value,
        ),
        # Liabilities
        AccountModel(
            company_id=company.id,
            code="50.00.00",
            name="Προμηθευτές Εσωτερικού",
            account_type=AccountType.LIABILITY.value,
        ),
        # Equity
        AccountModel(
            company_id=company.id,
            code="40.00.00",
            name="Κεφάλαιο",
            account_type=AccountType.EQUITY.value,
        ),
        AccountModel(
            company_id=company.id,
            code="40.00.01",
            name="Κέρδη εις νέον",
            account_type=AccountType.EQUITY.value,
        ),
        # Expenses
        AccountModel(
            company_id=company.id,
            code="64.00.00",
            name="Μισθοί",
            account_type=AccountType.EXPENSE.value,
        ),
        AccountModel(
            company_id=company.id,
            code="73.00.00",
            name="Παροχή Υπηρεσιών",
            account_type=AccountType.REVENUE.value,
        ),
    ]

    for account in accounts:
        session.add(account)
    await session.flush()
    print(f"  Created {len(accounts)} accounts")

    await session.commit()
    print("\n📋 Login credentials:")
    print("   Email: admin@demo.com")
    print("   Password: adminpass")


if __name__ == "__main__":
    asyncio.run(seed_database())
