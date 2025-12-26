"""Integration tests for accounts API."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_account(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test creating an account."""
    response = await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={
            "code": "1000",
            "name": "Cash",
            "account_type": "asset",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "1000"
    assert data["name"] == "Cash"
    assert data["account_type"] == "asset"


@pytest.mark.asyncio
async def test_create_duplicate_account_code(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test that duplicate account codes are rejected."""
    # Create first account
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={
            "code": "1000",
            "name": "Cash",
            "account_type": "asset",
        },
    )

    # Try to create duplicate
    response = await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={
            "code": "1000",
            "name": "Another Cash",
            "account_type": "asset",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_accounts(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test listing accounts."""
    # Create some accounts
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "2000", "name": "Accounts Payable", "account_type": "liability"},
    )

    response = await client.get(
        "/api/v1/accounts/",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_get_account(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test getting a specific account."""
    # Create account
    create_response = await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )
    account_id = create_response.json()["id"]

    response = await client.get(
        f"/api/v1/accounts/{account_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["code"] == "1000"


@pytest.mark.asyncio
async def test_update_account(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test updating an account."""
    # Create account
    create_response = await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )
    account_id = create_response.json()["id"]

    response = await client.patch(
        f"/api/v1/accounts/{account_id}",
        headers=auth_headers,
        json={"name": "Petty Cash"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Petty Cash"


@pytest.mark.asyncio
async def test_delete_account(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test deleting an account."""
    # Create account
    create_response = await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )
    account_id = create_response.json()["id"]

    response = await client.delete(
        f"/api/v1/accounts/{account_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204

    # Verify account is deleted
    get_response = await client.get(
        f"/api/v1/accounts/{account_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 404
