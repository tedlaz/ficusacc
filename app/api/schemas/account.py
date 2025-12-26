"""Account API schemas.

Note: Some field definitions appear similar to AccountBase in database/models/account.py.
This is intentional because:
1. AccountUpdate requires ALL fields to be optional (PATCH semantics)
2. AccountResponse must be a pure Pydantic model (no SQLAlchemy relationships)

AccountCreate uses AccountBase directly to avoid duplication.
"""

from datetime import datetime

from pydantic import BaseModel

from app.domain.types import AccountType
from app.infrastructure.database.models.account import AccountBase

# AccountCreate reuses AccountBase directly - no duplication
AccountCreate = AccountBase


class AccountUpdate(BaseModel):
    """Schema for updating an account.

    All fields optional for PATCH semantics - cannot inherit from AccountBase.
    """

    code: str | None = None
    name: str | None = None
    account_type: AccountType | None = None
    parent_id: int | None = None
    is_active: bool | None = None
    description: str | None = None


class AccountResponse(BaseModel):
    """Schema for account response.

    Pure Pydantic model - cannot use AccountModel due to SQLAlchemy relationships.
    """

    id: int
    company_id: int
    code: str
    name: str
    account_type: AccountType
    parent_id: int | None
    is_active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountListResponse(BaseModel):
    """Schema for list of accounts response."""

    items: list[AccountResponse]
    total: int


class AccountBulkCreateItem(BaseModel):
    """Schema for a single account in bulk create."""

    code: str
    name: str
    account_type: AccountType


class AccountBulkCreate(BaseModel):
    """Schema for bulk account creation."""

    accounts: list[AccountBulkCreateItem]


class AccountBulkCreateResponse(BaseModel):
    """Schema for bulk account creation response."""

    created: int
    errors: list[str]
