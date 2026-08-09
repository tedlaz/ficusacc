"""Create idempotent development data for the Flask application."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select

from app.core.security import hash_password
from app.domain.types import AccountType
from app.infrastructure.database.models import AccountModel, CompanyModel, UserCompanyAccessModel, UserModel
from app.main import app


def seed_database() -> None:
    with Session(app.extensions["sqlmodel_engine"]) as db:
        if db.exec(select(UserModel).where(UserModel.email == "admin@demo.com")).first():
            print("Demo data already exists.")
            return
        company = CompanyModel(name="DEMO", code="DEMO")
        user = UserModel(email="admin@demo.com", hashed_password=hash_password("adminpass"),
                         full_name="Admin User", is_superuser=True)
        db.add(company)
        db.add(user)
        db.flush()
        db.add(UserCompanyAccessModel(user_id=user.id, company_id=company.id, role="admin", is_default=True))
        accounts = [
            ("38.00.00", "Ταμείο", AccountType.ASSET),
            ("38.03.01", "Εθνική Τράπεζα", AccountType.ASSET),
            ("50.00.00", "Προμηθευτές Εσωτερικού", AccountType.LIABILITY),
            ("40.00.00", "Κεφάλαιο", AccountType.EQUITY),
            ("40.00.01", "Κέρδη εις νέον", AccountType.EQUITY),
            ("64.00.00", "Μισθοί", AccountType.EXPENSE),
            ("73.00.00", "Παροχή Υπηρεσιών", AccountType.REVENUE),
        ]
        for code, name, account_type in accounts:
            db.add(AccountModel(company_id=company.id, code=code, name=name, account_type=account_type))
        db.commit()
    print("Database seeded. Login: admin@demo.com / adminpass")


if __name__ == "__main__":
    seed_database()
