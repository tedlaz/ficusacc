"""Flask test fixtures backed by an isolated SQLite database."""

import pytest
from sqlmodel import Session

from app.core.security import hash_password
from app.infrastructure.database.models import CompanyModel, UserCompanyAccessModel, UserModel
from app.main import create_app


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
            "SECRET_KEY": "test-secret",
            "BACKUP_DIR": str(tmp_path / "backups"),
        }
    )
    yield application
    application.extensions["sqlmodel_engine"].dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf(client):
    with client.session_transaction() as session:
        session["csrf_token"] = "test-csrf"
    return "test-csrf"


@pytest.fixture
def seeded(app):
    with Session(app.extensions["sqlmodel_engine"]) as db:
        user = UserModel(
            email="admin@example.com",
            full_name="Test Admin",
            hashed_password=hash_password("testpassword"),
            is_superuser=True,
        )
        company = CompanyModel(name="Test Company", code="TEST", currency="EUR")
        db.add(user)
        db.add(company)
        db.flush()
        db.add(
            UserCompanyAccessModel(
                user_id=user.id,
                company_id=company.id,
                role="owner",
                is_default=True,
            )
        )
        db.commit()
        return user.id, company.id


@pytest.fixture
def logged_in(client, csrf, seeded):
    response = client.post(
        "/login",
        data={"csrf_token": csrf, "email": "admin@example.com", "password": "testpassword"},
    )
    assert response.status_code == 302
    return seeded
