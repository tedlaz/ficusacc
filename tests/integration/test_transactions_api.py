"""Integration tests for transactions API."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_transaction(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test creating a balanced transaction."""
    # Create accounts first
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "4000", "name": "Sales Revenue", "account_type": "revenue"},
    )

    # Get account IDs
    accounts_response = await client.get("/api/v1/accounts/", headers=auth_headers)
    accounts = accounts_response.json()["items"]
    cash_id = next(a["id"] for a in accounts if a["code"] == "1000")
    revenue_id = next(a["id"] for a in accounts if a["code"] == "4000")

    # Create transaction
    response = await client.post(
        "/api/v1/transactions/",
        headers=auth_headers,
        json={
            "transaction_date": "2024-01-15",
            "description": "Cash sale",
            "lines": [
                {"account_id": cash_id, "amount": "100.00"},
                {"account_id": revenue_id, "amount": "-100.00"},
            ],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["description"] == "Cash sale"
    assert len(data["lines"]) == 2


@pytest.mark.asyncio
async def test_create_unbalanced_transaction(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test that unbalanced transactions are rejected."""
    # Create accounts
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "4000", "name": "Sales Revenue", "account_type": "revenue"},
    )

    accounts_response = await client.get("/api/v1/accounts/", headers=auth_headers)
    accounts = accounts_response.json()["items"]
    cash_id = next(a["id"] for a in accounts if a["code"] == "1000")
    revenue_id = next(a["id"] for a in accounts if a["code"] == "4000")

    # Try to create unbalanced transaction
    response = await client.post(
        "/api/v1/transactions/",
        headers=auth_headers,
        json={
            "transaction_date": "2024-01-15",
            "description": "Unbalanced",
            "lines": [
                {"account_id": cash_id, "amount": "100.00"},
                {"account_id": revenue_id, "amount": "-50.00"},  # Doesn't balance
            ],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_single_line_transaction(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test that single-line transactions are rejected."""
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )

    accounts_response = await client.get("/api/v1/accounts/", headers=auth_headers)
    cash_id = accounts_response.json()["items"][0]["id"]

    response = await client.post(
        "/api/v1/transactions/",
        headers=auth_headers,
        json={
            "transaction_date": "2024-01-15",
            "description": "Single line",
            "lines": [
                {"account_id": cash_id, "amount": "100.00"},
            ],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_transaction(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test posting a transaction."""
    # Create accounts and transaction
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "4000", "name": "Sales", "account_type": "revenue"},
    )

    accounts_response = await client.get("/api/v1/accounts/", headers=auth_headers)
    accounts = accounts_response.json()["items"]
    cash_id = next(a["id"] for a in accounts if a["code"] == "1000")
    revenue_id = next(a["id"] for a in accounts if a["code"] == "4000")

    create_response = await client.post(
        "/api/v1/transactions/",
        headers=auth_headers,
        json={
            "transaction_date": "2024-01-15",
            "description": "Sale",
            "lines": [
                {"account_id": cash_id, "amount": "100.00"},
                {"account_id": revenue_id, "amount": "-100.00"},
            ],
        },
    )
    txn_id = create_response.json()["id"]

    # Post transaction
    response = await client.post(
        f"/api/v1/transactions/{txn_id}/post",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_posted"] is True


@pytest.mark.asyncio
async def test_cannot_update_posted_transaction(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test that posted transactions cannot be updated."""
    # Create and post transaction
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "1000", "name": "Cash", "account_type": "asset"},
    )
    await client.post(
        "/api/v1/accounts/",
        headers=auth_headers,
        json={"code": "4000", "name": "Sales", "account_type": "revenue"},
    )

    accounts_response = await client.get("/api/v1/accounts/", headers=auth_headers)
    accounts = accounts_response.json()["items"]
    cash_id = next(a["id"] for a in accounts if a["code"] == "1000")
    revenue_id = next(a["id"] for a in accounts if a["code"] == "4000")

    create_response = await client.post(
        "/api/v1/transactions/",
        headers=auth_headers,
        json={
            "transaction_date": "2024-01-15",
            "description": "Sale",
            "lines": [
                {"account_id": cash_id, "amount": "100.00"},
                {"account_id": revenue_id, "amount": "-100.00"},
            ],
        },
    )
    txn_id = create_response.json()["id"]

    await client.post(f"/api/v1/transactions/{txn_id}/post", headers=auth_headers)

    # Try to update
    response = await client.patch(
        f"/api/v1/transactions/{txn_id}",
        headers=auth_headers,
        json={"description": "Updated"},
    )
    assert response.status_code == 422
