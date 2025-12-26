"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.core.security import hash_password
from app.dependencies import get_db
from app.infrastructure.database.models import (
    CompanyModel,
    UserCompanyAccessModel,
    UserModel,
)
from app.main import app

# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestAsyncSession = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with TestAsyncSession() as session:
        yield session
        await session.rollback()

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with overridden dependencies."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> UserModel:
    """Create a test user."""
    user = UserModel(
        email="test@example.com",
        hashed_password=hash_password("testpassword"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_superuser(db_session: AsyncSession) -> UserModel:
    """Create a test superuser."""
    user = UserModel(
        email="admin@example.com",
        hashed_password=hash_password("adminpassword"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_company(db_session: AsyncSession) -> CompanyModel:
    """Create a test company."""
    company = CompanyModel(
        name="Test Company",
        code="TEST",
        fiscal_year_start_month=1,
        currency="USD",
        is_active=True,
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    return company


@pytest_asyncio.fixture
async def user_with_company_access(
    db_session: AsyncSession, test_user: UserModel, test_company: CompanyModel
) -> tuple[UserModel, CompanyModel, UserCompanyAccessModel]:
    """Create a user with access to a company."""
    access = UserCompanyAccessModel(
        user_id=test_user.id,
        company_id=test_company.id,
        role="owner",
        is_default=True,
    )
    db_session.add(access)
    await db_session.commit()
    await db_session.refresh(access)
    return test_user, test_company, access


@pytest_asyncio.fixture
async def auth_headers(
    client: AsyncClient,
    user_with_company_access: tuple[UserModel, CompanyModel, UserCompanyAccessModel],
) -> dict[str, str]:
    """Get authentication headers for a test user."""
    user, company, _ = user_with_company_access
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "testpassword",
            "company_id": company.id,
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
