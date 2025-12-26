"""Domain entities - re-exported from database models for backward compatibility."""

from app.domain.types import AccountType, UserRole
from app.infrastructure.database.models.account import AccountModel as Account
from app.infrastructure.database.models.company import (
    CompanyModel as Company,
)
from app.infrastructure.database.models.company import (
    UserCompanyAccessModel as UserCompanyAccess,
)
from app.infrastructure.database.models.transaction import (
    TransactionLineModel as TransactionLine,
)
from app.infrastructure.database.models.transaction import (
    TransactionModel as Transaction,
)
from app.infrastructure.database.models.user import UserModel as User

__all__ = [
    "Account",
    "AccountType",
    "Transaction",
    "TransactionLine",
    "User",
    "Company",
    "UserCompanyAccess",
    "UserRole",
]
