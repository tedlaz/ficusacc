"""Transaction management API routes."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)
from app.application.services import TransactionService
from app.core.exceptions import (
    EntityNotFoundError,
    InsufficientTransactionLinesError,
    TransactionNotBalancedError,
    ValidationError,
)
from app.dependencies import CurrentCompany, CurrentUser, get_transaction_service

router = APIRouter()


@router.post("/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    transaction_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    """
    Create a new transaction with journal entries.

    Transaction rules:
    - Must have at least 2 lines
    - Total debits must equal total credits (sum of amounts = 0)
    - Positive amounts are debits, negative are credits
    """
    try:
        transaction = await transaction_service.create_transaction(
            company_id=current_company.id,  # type: ignore
            user_id=current_user.id,  # type: ignore
            transaction_date=data.transaction_date,
            description=data.description,
            lines=[line.model_dump() for line in data.lines],
            reference=data.reference,
            is_posted=data.is_posted,
        )
        return TransactionResponse.model_validate(transaction)
    except (InsufficientTransactionLinesError, TransactionNotBalancedError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/", response_model=TransactionListResponse)
async def list_transactions(
    current_user: CurrentUser,
    current_company: CurrentCompany,
    transaction_service: Annotated[TransactionService, Depends(get_transaction_service)],
    skip: int = 0,
    limit: int = 100,
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: int | None = None,
    posted_only: bool = False,
    draft_only: bool = False,
) -> TransactionListResponse:
    """
    List transactions for the current company.

    Filters:
    - start_date, end_date: Filter by date range
    - account_id: Filter by account
    - posted_only: Only return posted transactions
    - draft_only: Only return draft transactions
    """
    if start_date and end_date:
        transactions = await transaction_service.get_transactions_by_date_range(
            current_company.id,
            start_date,
            end_date,  # type: ignore
        )
    elif account_id:
        transactions = await transaction_service.get_transactions_by_account(
            current_company.id,
            account_id,
            start_date,
            end_date,  # type: ignore
        )
    elif posted_only:
        transactions = await transaction_service.get_posted_transactions(
            current_company.id,
            skip,
            limit,  # type: ignore
        )
    elif draft_only:
        transactions = await transaction_service.get_draft_transactions(
            current_company.id,
            skip,
            limit,  # type: ignore
        )
    else:
        transactions = await transaction_service.get_transactions(
            current_company.id,
            skip,
            limit,  # type: ignore
        )

    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in transactions],
        total=len(transactions),
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    transaction_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    """Get a transaction by ID."""
    try:
        transaction = await transaction_service.get_transaction(
            current_company.id,
            transaction_id,  # type: ignore
        )
        return TransactionResponse.model_validate(transaction)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    data: TransactionUpdate,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    transaction_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    """
    Update a transaction.

    Note: Posted transactions cannot be updated.
    """
    try:
        transaction = await transaction_service.update_transaction(
            company_id=current_company.id,  # type: ignore
            transaction_id=transaction_id,
            transaction_date=data.transaction_date,
            description=data.description,
            reference=data.reference,
            lines=[line.model_dump() for line in data.lines] if data.lines else None,
        )
        return TransactionResponse.model_validate(transaction)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except (InsufficientTransactionLinesError, TransactionNotBalancedError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)


@router.post("/{transaction_id}/post", response_model=TransactionResponse)
async def post_transaction(
    transaction_id: int,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    transaction_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    """
    Post a transaction (finalize it).

    Posted transactions cannot be edited or deleted.
    """
    try:
        transaction = await transaction_service.post_transaction(
            current_company.id,
            transaction_id,  # type: ignore
        )
        return TransactionResponse.model_validate(transaction)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)


@router.post("/{transaction_id}/unpost", response_model=TransactionResponse)
async def unpost_transaction(
    transaction_id: int,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    transaction_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    """
    Unpost a transaction (revert to draft).

    This allows the transaction to be edited or deleted again.
    """
    try:
        transaction = await transaction_service.unpost_transaction(
            current_company.id,
            transaction_id,  # type: ignore
        )
        return TransactionResponse.model_validate(transaction)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: int,
    current_user: CurrentUser,
    current_company: CurrentCompany,
    transaction_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> None:
    """
    Delete a transaction.

    Note: Posted transactions cannot be deleted.
    """
    try:
        await transaction_service.delete_transaction(
            current_company.id,
            transaction_id,  # type: ignore
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
