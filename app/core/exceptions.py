"""Custom exceptions for the application."""


class AppException(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class EntityNotFoundError(AppException):
    """Raised when an entity is not found."""

    def __init__(self, entity_type: str, entity_id: int | str):
        super().__init__(
            message=f"{entity_type} with ID {entity_id} not found",
            status_code=404,
        )


class DuplicateEntityError(AppException):
    """Raised when attempting to create a duplicate entity."""

    def __init__(self, entity_type: str, field: str, value: str):
        super().__init__(
            message=f"{entity_type} with {field} '{value}' already exists",
            status_code=409,
        )


class ValidationError(AppException):
    """Raised when validation fails."""

    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)


class AuthenticationError(AppException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message=message, status_code=401)


class AuthorizationError(AppException):
    """Raised when authorization fails."""

    def __init__(self, message: str = "Not authorized to perform this action"):
        super().__init__(message=message, status_code=403)


class TransactionNotBalancedError(ValidationError):
    """Raised when a transaction does not balance."""

    def __init__(self, difference: str):
        super().__init__(
            message=f"Transaction does not balance. Difference: {difference}. "
            "Total debits must equal total credits."
        )


class InsufficientTransactionLinesError(ValidationError):
    """Raised when a transaction has fewer than 2 lines."""

    def __init__(self):
        super().__init__(message="Transaction must have at least 2 lines")
