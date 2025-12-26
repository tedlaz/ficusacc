"""Integration tests for authentication API."""

import pytest
from httpx import AsyncClient

from app.infrastructure.database.models import CompanyModel, UserModel


@pytest.mark.asyncio
async def test_login_success(
    client: AsyncClient,
    user_with_company_access: tuple[UserModel, CompanyModel, ...],
):
    """Test successful login."""
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
    data = response.json()
    assert "access_token" in data
    assert data["user_id"] == user.id
    assert data["company_id"] == company.id


@pytest.mark.asyncio
async def test_login_invalid_password(
    client: AsyncClient,
    user_with_company_access: tuple[UserModel, CompanyModel, ...],
):
    """Test login with invalid password."""
    user, _, _ = user_with_company_access
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "wrongpassword",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_invalid_email(client: AsyncClient):
    """Test login with non-existent email."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "password",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_companies(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test getting user's accessible companies."""
    response = await client.get(
        "/api/v1/auth/companies",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_switch_company(
    client: AsyncClient,
    auth_headers: dict[str, str],
    user_with_company_access: tuple[UserModel, CompanyModel, ...],
):
    """Test switching to a different company."""
    _, company, _ = user_with_company_access
    response = await client.post(
        "/api/v1/auth/switch-company",
        headers=auth_headers,
        json={"company_id": company.id},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["company_id"] == company.id
