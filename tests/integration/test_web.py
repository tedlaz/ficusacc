"""End-to-end tests for server-rendered Flask workflows."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import re
from urllib.parse import quote

from sqlmodel import Session, select

from app.infrastructure.database.models import (
    AccountModel,
    TransactionLineModel,
    TransactionModel,
    UserModel,
)
from app.web.routes import database_path


def test_health_and_auth_guards(client):
    assert client.get("/health").json["status"] == "healthy"
    response = client.get("/")
    assert response.status_code == 302
    assert response.location.startswith("/login")
    assert "Είσοδος λογαριασμού" in client.get("/login").text


def test_dashboard_uses_company_history_cash_balances_and_database_order(
    client, logged_in, app
):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(
            company_id=company_id,
            code="38.00.01",
            name="Κεντρικό Ταμείο",
            account_type="asset",
        )
        counter = AccountModel(
            company_id=company_id,
            code="50.00.01",
            name="Προμηθευτές",
            account_type="liability",
        )
        db.add(cash)
        db.add(counter)
        db.flush()
        for index in range(12):
            transaction = TransactionModel(
                company_id=company_id,
                created_by_id=user_id,
                transaction_date=date(2026, 1, 12) - timedelta(days=index),
                description=f"Overview entry {index:02d}",
                is_posted=True,
            )
            db.add(transaction)
            db.flush()
            db.add(
                TransactionLineModel(
                    transaction_id=transaction.id,
                    account_id=cash.id,
                    amount=1,
                    line_order=0,
                )
            )
            db.add(
                TransactionLineModel(
                    transaction_id=transaction.id,
                    account_id=counter.id,
                    amount=-1,
                    line_order=1,
                )
            )
        db.commit()
        newest_id = transaction.id

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "<h1>Επισκόπηση</h1>" in dashboard.text
    assert "Πρώτη ημερομηνία εγγραφής · 01/01/2026" in dashboard.text
    assert "Ταμιακά διαθέσιμα" in dashboard.text
    assert "Βασικοί λογαριασμοί" not in dashboard.text
    assert "Σύνολο ενεργητικού" not in dashboard.text
    assert "Υποχρεώσεις" not in dashboard.text
    assert "38.00.01" in dashboard.text
    assert "Κεντρικό Ταμείο" in dashboard.text
    assert "12,00 €" in dashboard.text
    assert "cash-total-row" in dashboard.text
    assert "data-flow-chart" in dashboard.text
    assert "data-cash-chart" not in dashboard.text
    assert "Ροή χρημάτων" in dashboard.text
    assert "Ταμείο τώρα" in dashboard.text
    assert (
        'data-month="2026-01" data-label="Ιαν 2026" data-revenue="0.00" data-expenses="0.00" '
        'data-net="0.00" data-cash-in="12.00" data-cash-out="0.00"'
    ) in dashboard.text
    assert dashboard.text.count("data-dashboard-transaction") == 10
    assert dashboard.text.index("Overview entry 11") < dashboard.text.index("Overview entry 10")
    assert "<strong>Overview entry 00</strong>" not in dashboard.text
    assert "<strong>Overview entry 01</strong>" not in dashboard.text
    assert f'data-modal-url="/transactions/{newest_id}"' in dashboard.text
    assert f'data-transaction-preview-url="/transactions/{newest_id}/preview"' in dashboard.text


def test_first_registration_creates_superuser_and_company(client, csrf, app):
    response = client.post(
        "/register",
        data={
            "csrf_token": csrf,
            "full_name": "First User",
            "email": "first@example.com",
            "password": "secret1",
            "company_name": "Acme",
        },
    )
    assert response.status_code == 302
    assert client.get("/").status_code == 200
    with Session(app.extensions["sqlmodel_engine"]) as db:
        user = db.exec(select(UserModel).where(UserModel.email == "first@example.com")).one()
        assert user.is_superuser is True


def test_login_rejects_bad_password(client, csrf, seeded):
    response = client.post(
        "/login",
        data={"csrf_token": csrf, "email": "admin@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
    assert "Λανθασμένο" in response.text


def test_account_crud_and_csv(client, csrf, logged_in, app):
    response = client.post(
        "/accounts/new",
        data={
            "csrf_token": csrf,
            "code": "1000",
            "name": "Ταμείο",
            "account_type": "asset",
        },
    )
    assert response.status_code == 302
    page = client.get("/accounts")
    assert page.status_code == 200
    assert "Ταμείο" in page.text
    exported = client.get("/accounts/export")
    assert exported.status_code == 200
    assert '"1000","Ταμείο","asset"' in exported.text

    imported = client.post(
        "/accounts/import",
        data={"csrf_token": csrf, "file": (bytes_io("code,name,account_type\n2000,Πωλήσεις,revenue"), "accounts.csv")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 302
    with Session(app.extensions["sqlmodel_engine"]) as db:
        assert len(list(db.exec(select(AccountModel)).all())) == 2

    # Parents: explicit 4th column, auto-link by code prefix (even when the header comes later), unknown parent.
    rows = "\n".join((
        "code,name,account_type,parent_code",
        '"10.00.01","Μετρητά, ταμείο","asset",',
        '"10","Ταμειακά","asset",',
        '"10.00.02","Κάρτα","asset","10"',
        '"10.00.03","Άγνωστος","asset","99"',
    ))
    imported = client.post("/accounts/import", data={"csrf_token": csrf, "file": (bytes_io(rows), "a.csv")},
                           content_type="multipart/form-data")
    assert imported.status_code == 302
    with Session(app.extensions["sqlmodel_engine"]) as db:
        by_code = {a.code: a for a in db.exec(select(AccountModel)).all()}
    assert by_code["10.00.01"].name == "Μετρητά, ταμείο"
    assert by_code["10.00.01"].parent_id == by_code["10"].id
    assert by_code["10.00.02"].parent_id == by_code["10"].id
    assert by_code["10.00.03"].parent_id == by_code["10"].id  # unknown parent falls back to the prefix
    assert by_code["10"].parent_id is None
    exported = client.get("/accounts/export")
    assert '"10.00.02","Κάρτα","asset","10"' in exported.text
    assert '"10","Ταμειακά","asset",""' in exported.text
    page = client.get("/accounts")
    assert '<span class="code" title="Ταμειακά">10</span>' in page.text

    # Form: empty parent on a new account is auto-suggested; self-parent is rejected on edit.
    response = client.post("/accounts/new", data={"csrf_token": csrf, "code": "10.00.04", "name": "Νέος",
                                                  "account_type": "asset", "parent_id": ""})
    assert response.status_code == 302
    with Session(app.extensions["sqlmodel_engine"]) as db:
        new = db.exec(select(AccountModel).where(AccountModel.code == "10.00.04")).one()
        assert new.parent_id == by_code["10"].id
        new_id = new.id
    response = client.post(f"/accounts/{new_id}/edit", data={"csrf_token": csrf, "code": "10.00.04", "name": "Νέος",
                                                            "account_type": "asset", "parent_id": str(new_id),
                                                            "editing": "1", "is_active": "on"})
    assert response.status_code == 422


def test_balanced_transaction_post_and_reports(client, csrf, logged_in, app):
    company_id = logged_in[1]
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="1000", name="Cash", account_type="asset")
        revenue = AccountModel(company_id=company_id, code="7000", name="Revenue", account_type="revenue")
        db.add(cash)
        db.add(revenue)
        db.commit()
        db.refresh(cash)
        db.refresh(revenue)
        cash_id, revenue_id = cash.id, revenue.id

    response = client.post(
        "/transactions/new",
        data={
            "csrf_token": csrf,
            "transaction_date": "15/01/2026",
            "description": "Sale",
            "reference": "INV-1",
            "account_id": [str(cash_id), str(revenue_id)],
            "amount": ["100.00", "-100.00"],
            "line_description": ["", ""],
        },
    )
    assert response.status_code == 302
    with Session(app.extensions["sqlmodel_engine"]) as db:
        transaction = db.exec(select(TransactionModel)).one()
        transaction_id = transaction.id
        assert transaction.transaction_date == date(2026, 1, 15)
    assert client.post(f"/transactions/{transaction_id}/post", data={"csrf_token": csrf}).status_code == 302
    page = client.get("/transactions")
    assert page.status_code == 200
    assert 'data-tooltip="Προβολή"' in page.text
    assert f'data-transaction-preview-url="/transactions/{transaction_id}/preview"' in page.text
    assert 'data-tooltip="Αντιγραφή"' in page.text
    assert 'data-tooltip="Αναίρεση οριστικοποίησης"' in page.text
    assert "data-modal-url" in page.text
    new_form = client.get("/transactions/new", headers={"HX-Request": "true"})
    assert new_form.status_code == 200
    assert "data-auto-balance" in new_form.text
    assert client.get(f"/transactions/{transaction_id}", headers={"HX-Request": "true"}).status_code == 200
    preview = client.get(f"/transactions/{transaction_id}/preview")
    assert preview.status_code == 200
    assert "transaction-preview-card" in preview.text
    assert "Sale" in preview.text
    assert "Cash" in preview.text
    copy_form = client.get(f"/transactions/{transaction_id}/copy", headers={"HX-Request": "true"})
    assert copy_form.status_code == 200
    assert "data-auto-balance" in copy_form.text
    report = client.get("/reports/result?report_type=trial_balance&as_of_date=31/01/2026")
    assert report.status_code == 200
    assert "100,00 €" in report.text
    assert "100,00 EUR" not in report.text
    assert "Ισοζύγιο" in report.text
    assert f'href="/accounts/{cash_id}/ledger"' in report.text
    response = client.post(
        f"/transactions/{transaction_id}/unpost",
        data={"csrf_token": csrf},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/transactions"
    edit_form = client.get(
        f"/transactions/{transaction_id}/edit", headers={"HX-Request": "true"}
    )
    assert edit_form.status_code == 200
    assert "data-auto-balance" in edit_form.text
    response = client.post(
        f"/transactions/{transaction_id}/edit",
        data={
            "csrf_token": csrf,
            "transaction_date": "16/01/2026",
            "description": "Updated sale",
            "reference": "INV-2",
            "account_id": [str(cash_id), str(revenue_id)],
            "amount": ["125.00", "-125.00"],
            "line_description": ["", ""],
        },
    )
    assert response.status_code == 302
    with Session(app.extensions["sqlmodel_engine"]) as db:
        transaction = db.get(TransactionModel, transaction_id)
        assert transaction.is_posted is False
        assert transaction.transaction_date == date(2026, 1, 16)
        assert transaction.description == "Updated sale"
        assert transaction.reference == "INV-2"
        assert [line.amount for line in transaction.lines] == [125, -125]


def test_unbalanced_transaction_is_rejected(client, csrf, logged_in, app):
    company_id = logged_in[1]
    with Session(app.extensions["sqlmodel_engine"]) as db:
        one = AccountModel(company_id=company_id, code="1", name="One", account_type="asset")
        two = AccountModel(company_id=company_id, code="2", name="Two", account_type="liability")
        db.add(one)
        db.add(two)
        db.commit()
        db.refresh(one)
        db.refresh(two)
    response = client.post(
        "/transactions/new",
        data={"csrf_token": csrf, "transaction_date": "2026-01-15", "description": "Bad",
              "account_id": [str(one.id), str(two.id)], "amount": ["10", "-5"],
              "line_description": ["", ""]},
    )
    assert response.status_code == 422
    assert "δεν ισοσκελίζεται" in response.text


def test_company_user_and_backup_pages_render(client, csrf, logged_in):
    assert client.get("/companies").status_code == 200
    assert client.get("/users").status_code == 200
    assert client.get("/backup").status_code == 200
    response = client.post("/backup/create", data={"csrf_token": csrf})
    assert response.status_code == 302
    assert "accounting_backup_" in client.get("/backup").text
    response = client.get("/backup/download")
    assert response.status_code == 200
    assert response.data.startswith(b"SQLite format 3")


def test_database_path_preserves_absolute_sqlite_path(app):
    with app.app_context():
        app.config["DATABASE_URL"] = "sqlite:////app/data/accounting.db"
        assert database_path() == Path("/app/data/accounting.db").resolve()


def test_all_reports_download_as_fpdf2_documents(client, logged_in, app):
    _, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        account = AccountModel(
            company_id=company_id,
            code="38.00.01",
            name="Ταμείο",
            account_type="asset",
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        account_id = account.id

    urls = (
        "/reports/pdf?report_type=trial_balance&as_of_date=31/01/2026",
        "/reports/pdf?report_type=balance_sheet&as_of_date=31/01/2026",
        "/reports/pdf?report_type=income_statement&start_date=01/01/2026&end_date=31/01/2026",
        "/reports/pdf?report_type=journal&start_date=01/01/2026&end_date=31/01/2026",
        f"/reports/pdf?report_type=general_ledger&account_id={account_id}",
    )
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert response.data.startswith(b"%PDF")
        assert b"/MediaBox [0 0 595.28 841.89]" in response.data
        assert len(response.data) > 1000
        assert ".pdf" in response.headers["Content-Disposition"]

    reports_page = client.get("/reports")
    assert "data-pdf-url=\"/reports/pdf\"" in reports_page.text
    assert "data-export-pdf" in reports_page.text
    assert "aria-disabled" not in reports_page.text
    assert "html2canvas" not in reports_page.text
    assert "jspdf" not in reports_page.text.lower()


def test_accounts_transactions_and_journal_are_paginated(
    client, logged_in, app, monkeypatch
):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        for index in range(30):
            db.add(
                AccountModel(
                    company_id=company_id,
                    code=f"{index:04d}",
                    name=f"Account {index}",
                    account_type="asset",
                )
            )
            db.add(
                TransactionModel(
                    company_id=company_id,
                    created_by_id=user_id,
                    transaction_date=date(2026, 1, 15),
                    description=f"Transaction {index}",
                )
            )
        db.commit()

    first_accounts = client.get("/accounts")
    second_accounts = client.get("/accounts?page=2")
    assert first_accounts.text.count("data-account-row") == 25
    assert second_accounts.text.count("data-account-row") == 5
    assert 'aria-current="page">1</span>' in first_accounts.text
    assert 'href="?page=2"' in first_accounts.text

    first_transactions = client.get("/transactions")
    second_transactions = client.get("/transactions?page=2")
    assert first_transactions.text.count("data-transaction-row") == 25
    assert second_transactions.text.count("data-transaction-row") == 5
    assert 'aria-current="page">2</span>' in second_transactions.text
    assert 'href="?page=1"' in second_transactions.text

    journal_url = (
        "/reports/result?report_type=journal&start_date=01/01/2026&end_date=31/01/2026"
    )
    first_journal = client.get(journal_url)
    second_journal = client.get(f"{journal_url}&page=2")
    assert first_journal.status_code == 200
    assert first_journal.text.count("data-journal-article") == 25
    assert second_journal.text.count("data-journal-article") == 5
    assert first_journal.text.index("Transaction 29") < first_journal.text.index("Transaction 28")
    assert second_journal.text.index("Transaction 4") < second_journal.text.index("Transaction 3")
    assert 'aria-current="page">1</span>' in first_journal.text
    assert 'hx-get="/reports/result?report_type=journal&amp;start_date=01/01/2026&amp;end_date=31/01/2026&amp;page=2"' in first_journal.text

    captured = {}

    def capture_pdf(kind, data, company):
        captured["kind"] = kind
        captured["entries"] = len(data["entries"])
        return b"%PDF-full-journal", "journal.pdf"

    monkeypatch.setattr("app.web.routes.build_report_pdf", capture_pdf)
    pdf = client.get(
        "/reports/pdf?report_type=journal&start_date=01/01/2026&end_date=31/01/2026"
    )
    assert pdf.status_code == 200
    assert captured == {"kind": "journal", "entries": 30}


def test_account_ledger_is_clickable_paginated_and_newest_first(client, logged_in, app):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        account = AccountModel(company_id=company_id, code="1000", name="Cash", account_type="asset")
        counter = AccountModel(company_id=company_id, code="3000", name="Equity", account_type="equity")
        db.add(account)
        db.add(counter)
        db.flush()
        for index in range(30):
            transaction = TransactionModel(
                company_id=company_id,
                created_by_id=user_id,
                transaction_date=date(2026, 1, 1) + timedelta(days=index),
                description=f"Ledger entry {index:02d}",
                is_posted=True,
            )
            db.add(transaction)
            db.flush()
            amount = index + 1
            db.add(
                TransactionLineModel(
                    transaction_id=transaction.id,
                    account_id=account.id,
                    amount=amount,
                    line_order=0,
                )
            )
            db.add(
                TransactionLineModel(
                    transaction_id=transaction.id,
                    account_id=counter.id,
                    amount=-amount,
                    line_order=1,
                )
            )
        newest_transaction_id = transaction.id
        draft = TransactionModel(
            company_id=company_id,
            created_by_id=user_id,
            transaction_date=date(2026, 2, 1),
            description="Draft entry",
            is_posted=False,
        )
        db.add(draft)
        db.flush()
        db.add(
            TransactionLineModel(
                transaction_id=draft.id,
                account_id=account.id,
                amount=999,
                line_order=0,
            )
        )
        db.commit()
        account_id = account.id

    accounts_page = client.get("/accounts")
    assert f'/accounts/{account_id}/ledger' in accounts_page.text

    first_page = client.get(f"/accounts/{account_id}/ledger")
    second_page = client.get(f"/accounts/{account_id}/ledger?page=2")
    assert first_page.status_code == 200
    assert first_page.text.count("data-ledger-row") == 25
    assert second_page.text.count("data-ledger-row") == 5
    assert first_page.text.index("Ledger entry 29") < first_page.text.index("Ledger entry 28")
    assert f'data-modal-url="/transactions/{newest_transaction_id}"' in first_page.text
    assert second_page.text.index("Ledger entry 04") < second_page.text.index("Ledger entry 03")
    assert "465,00 €" in first_page.text
    assert "Draft entry" not in first_page.text
    assert 'name="start_date"' not in first_page.text
    assert 'name="end_date"' not in first_page.text

    report_first = client.get(
        f"/reports/result?report_type=general_ledger&account_id={account_id}"
    )
    report_second = client.get(
        f"/reports/result?report_type=general_ledger&account_id={account_id}&page=2"
    )
    assert report_first.status_code == 200
    assert report_first.text.count("data-report-ledger-row") == 25
    assert report_second.text.count("data-report-ledger-row") == 5
    assert report_first.text.index("Ledger entry 29") < report_first.text.index("Ledger entry 28")
    assert "465,00 €" in report_first.text
    assert "Draft entry" not in report_first.text
    assert 'name="start_date"' not in report_first.text
    assert 'name="end_date"' not in report_first.text
    assert "report_type=general_ledger" in report_first.text
    assert f'data-modal-url="/transactions/{newest_transaction_id}"' in report_first.text

    detail = client.get(
        f"/transactions/{newest_transaction_id}", headers={"HX-Request": "true"}
    )
    assert detail.status_code == 200
    assert "data-transaction-form" not in detail.text
    assert f'data-modal-url="/transactions/{newest_transaction_id}/copy"' in detail.text
    assert "Δημιουργία παρόμοιας εγγραφής" in detail.text


def test_account_list_shows_balance_and_prevents_deleting_used_accounts(
    client, csrf, logged_in, app
):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        moved = AccountModel(company_id=company_id, code="1000", name="Moved", account_type="asset")
        draft_only = AccountModel(
            company_id=company_id, code="1100", name="Draft only", account_type="asset"
        )
        counter = AccountModel(company_id=company_id, code="3000", name="Counter", account_type="equity")
        unused = AccountModel(company_id=company_id, code="9000", name="Unused", account_type="expense")
        db.add(moved)
        db.add(draft_only)
        db.add(counter)
        db.add(unused)
        db.flush()

        posted = TransactionModel(
            company_id=company_id,
            created_by_id=user_id,
            transaction_date=date(2026, 1, 1),
            description="Posted movement",
            is_posted=True,
        )
        draft = TransactionModel(
            company_id=company_id,
            created_by_id=user_id,
            transaction_date=date(2026, 1, 2),
            description="Draft movement",
            is_posted=False,
        )
        db.add(posted)
        db.add(draft)
        db.flush()
        db.add(TransactionLineModel(transaction_id=posted.id, account_id=moved.id, amount=125))
        db.add(TransactionLineModel(transaction_id=posted.id, account_id=counter.id, amount=-125))
        db.add(TransactionLineModel(transaction_id=draft.id, account_id=draft_only.id, amount=50))
        db.add(TransactionLineModel(transaction_id=draft.id, account_id=counter.id, amount=-50))
        db.commit()
        moved_id, draft_only_id, unused_id = moved.id, draft_only.id, unused.id

    page = client.get("/accounts")
    assert "125,00 €" in page.text
    assert f'/accounts/{moved_id}/delete' not in page.text
    assert f'/accounts/{draft_only_id}/delete' not in page.text
    assert f'/accounts/{unused_id}/delete' in page.text

    blocked = client.post(
        f"/accounts/{moved_id}/delete",
        data={"csrf_token": csrf},
        follow_redirects=True,
    )
    assert blocked.status_code == 200
    assert "έχει κινήσεις και δεν μπορεί να διαγραφεί" in blocked.text
    with Session(app.extensions["sqlmodel_engine"]) as db:
        assert db.get(AccountModel, moved_id) is not None

    deleted = client.post(f"/accounts/{unused_id}/delete", data={"csrf_token": csrf})
    assert deleted.status_code == 302
    with Session(app.extensions["sqlmodel_engine"]) as db:
        assert db.get(AccountModel, unused_id) is None


def test_trial_balance_builds_dotted_account_summary_levels(client, logged_in, app):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(
            company_id=company_id, code="38.00.01", name="Cash", account_type="asset"
        )
        bank = AccountModel(
            company_id=company_id, code="38.00.02", name="Bank", account_type="asset"
        )
        counter = AccountModel(
            company_id=company_id, code="50.00.01", name="Supplier", account_type="liability"
        )
        group = AccountModel(company_id=company_id, code="38", name="Χρηματικά διαθέσιμα", account_type="asset")
        db.add(group)
        db.flush()
        subgroup = AccountModel(company_id=company_id, code="38.00", name="Ταμείο και τράπεζες",
                                account_type="asset", parent_id=group.id)
        db.add(subgroup)
        db.flush()
        cash.parent_id = bank.parent_id = subgroup.id
        db.add(cash)
        db.add(bank)
        db.add(counter)
        db.flush()
        for index, (account, amount) in enumerate(((cash, 100), (bank, 50))):
            transaction = TransactionModel(
                company_id=company_id,
                created_by_id=user_id,
                transaction_date=date(2026, 1, index + 1),
                description=f"Movement {index}",
                is_posted=True,
            )
            db.add(transaction)
            db.flush()
            db.add(
                TransactionLineModel(
                    transaction_id=transaction.id, account_id=account.id, amount=amount
                )
            )
            db.add(
                TransactionLineModel(
                    transaction_id=transaction.id, account_id=counter.id, amount=-amount
                )
            )
        db.commit()
        cash_id, bank_id = cash.id, bank.id

    response = client.get("/reports/result?report_type=trial_balance&as_of_date=2026-01-31")
    assert response.status_code == 200
    codes = ["38", "38.00", "38.00.01", "38.00.02"]
    positions = [response.text.index(f'data-trial-code="{code}"') for code in codes]
    assert positions == sorted(positions)

    summary_38 = re.search(
        r'<tr class="trial-summary-row" data-trial-code="38">(.*?)</tr>',
        response.text,
        re.DOTALL,
    ).group(1)
    summary_3800 = re.search(
        r'<tr class="trial-summary-row" data-trial-code="38\.00">(.*?)</tr>',
        response.text,
        re.DOTALL,
    ).group(1)
    assert summary_38.count("150,00 €") == 2
    assert summary_3800.count("150,00 €") == 2
    assert "Χρηματικά διαθέσιμα" in summary_38
    assert "Ταμείο και τράπεζες" in summary_3800
    assert "Σύνολο 38" not in response.text
    assert f'href="/accounts/{cash_id}/ledger"' in response.text
    assert f'href="/accounts/{bank_id}/ledger"' in response.text
    assert "/accounts/None/ledger" not in response.text

    footer = re.search(r"<tfoot>(.*?)</tfoot>", response.text, re.DOTALL).group(1)
    assert footer.count("150,00 €") == 2


def test_form_actions_are_icon_only(client, logged_in):
    for url in ("/accounts/new", "/companies/new", "/users/new", "/profile/password", "/reports", "/transactions/quick"):
        page = client.get(url)
        assert page.status_code == 200
        assert 'class="button' not in page.text
        assert "data-tooltip" in page.text


def test_modal_forms_only_close_from_explicit_buttons(client, logged_in):
    modal = client.get("/transactions/new", headers={"HX-Request": "true"})
    assert modal.status_code == 200
    assert '<div class="modal-scrim" aria-hidden="true"></div>' in modal.text
    assert "modal-scrim\" data-modal-close" not in modal.text
    assert "data-modal-close" in modal.text


def test_all_date_inputs_use_greek_format(client, logged_in):
    transaction_form = client.get("/transactions/new", headers={"HX-Request": "true"})
    reports_page = client.get("/reports")
    assert transaction_form.status_code == 200
    assert reports_page.status_code == 200
    assert transaction_form.text.count("data-greek-date") == 1
    assert reports_page.text.count("data-greek-date") == 3
    assert transaction_form.text.count("data-native-date") == 1
    assert reports_page.text.count("data-native-date") == 3
    assert transaction_form.text.count("data-date-picker") == 1
    assert reports_page.text.count("data-date-picker") == 3
    assert 'placeholder="ηη/μμ/εεεε"' in transaction_form.text
    assert 'pattern="[0-9]{2}/[0-9]{2}/[0-9]{4}"' in reports_page.text


def test_csrf_is_required(client, seeded):
    assert client.post("/login", data={"email": "admin@example.com"}).status_code == 400


def bytes_io(value: str):
    from io import BytesIO

    return BytesIO(value.encode("utf-8"))


def test_accounts_mapping_skeleton_export(client, csrf, logged_in):
    for code, name in (("38.00.00", "Ταμείο μετρητά"), ("33.00", "Απαιτήσεις")):
        assert client.post(
            "/accounts/new",
            data={"csrf_token": csrf, "code": code, "name": name, "account_type": "asset"},
        ).status_code == 302

    exported = client.get("/accounts/export/mapping")

    assert exported.status_code == 200
    assert "attachment; filename=metatropi_TEST.txt" in exported.headers["Content-Disposition"]
    assert exported.data.decode("utf-8").split("\r\n")[:2] == [
        "33.00     Απαιτήσεις",
        "38.00.00  Ταμείο μετρητά",
    ]


def posted_transaction(client, csrf, app, company_id):
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00.00", name="Ταμείο",
                            account_type="asset")
        revenue = AccountModel(company_id=company_id, code="70.00.00", name="Έσοδα",
                               account_type="revenue")
        db.add(cash)
        db.add(revenue)
        db.commit()
        db.refresh(cash)
        db.refresh(revenue)
        cash_id, revenue_id = cash.id, revenue.id

    assert client.post(
        "/transactions/new",
        data={
            "csrf_token": csrf,
            "transaction_date": "19/01/2026",
            "description": "Είσπραξη",
            "reference": "110",
            "account_id": [str(cash_id), str(revenue_id)],
            "amount": ["122.40", "-122.40"],
            "line_description": ["", ""],
        },
    ).status_code == 302
    with Session(app.extensions["sqlmodel_engine"]) as db:
        transaction_id = db.exec(select(TransactionModel)).one().id
    assert client.post(
        f"/transactions/{transaction_id}/post", data={"csrf_token": csrf}
    ).status_code == 302


def test_journal_export_produces_the_ledger_file(client, csrf, logged_in, app):
    posted_transaction(client, csrf, app, logged_in[1])
    mapping = "38.00.00  Ταμείο.Μετρητά\n70.00.00  Εσοδα.Κοινόχρηστα\n"

    exported = client.post(
        "/transactions/export/journal",
        data={
            "csrf_token": csrf,
            "start_date": "01/01/2026",
            "end_date": "31/12/2026",
            "mapping": (bytes_io(mapping), "metatropi.txt"),
        },
        content_type="multipart/form-data",
    )

    assert exported.status_code == 200
    assert "filename=journal_2026-01-01_2026-12-31.txt" in exported.headers["Content-Disposition"]
    assert exported.data.decode("utf-8") == (
        "j-normal\r\n"
        "\r\n"
        "2026-01-19 {110} Είσπραξη\r\n"
        "  Ταμείο.Μετρητά        122,40\r\n"
        "  Εσοδα.Κοινόχρηστα\r\n"
        "\r\n"
    )


def test_journal_export_stops_when_a_mapping_is_missing(client, csrf, logged_in, app):
    posted_transaction(client, csrf, app, logged_in[1])

    exported = client.post(
        "/transactions/export/journal",
        data={
            "csrf_token": csrf,
            "start_date": "01/01/2026",
            "end_date": "31/12/2026",
            "mapping": (bytes_io("38.00.00  Ταμείο.Μετρητά\n"), "metatropi.txt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert exported.status_code == 200
    assert "70.00.00" in exported.text


def _quick_accounts(app, company_id, inactive=False):
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00", name="Ταμείο", account_type="asset")
        revenue = AccountModel(company_id=company_id, code="70.00", name="Πωλήσεις", account_type="revenue",
                               is_active=not inactive)
        db.add(cash)
        db.add(revenue)
        db.commit()
        db.refresh(cash)
        db.refresh(revenue)
        return cash.id, revenue.id


def _quick_payload(csrf, cash_id, revenue_id, **overrides):
    payload = {
        "csrf_token": csrf,
        "mode": "draft",
        "row_date": ["15/01/2026", "16/01/2026", "16/01/2026", "16/01/2026"],
        "row_description": ["Είσπραξη Α", "Είσπραξη Β", "", ""],
        "row_debit": [str(cash_id), str(cash_id), "", ""],
        "row_credit": [str(revenue_id), str(revenue_id), "", ""],
        "row_amount": ["10", "20.50", "", ""],
    }
    payload.update(overrides)
    return payload


def _transactions(app):
    with Session(app.extensions["sqlmodel_engine"]) as db:
        items = list(db.exec(select(TransactionModel).order_by(TransactionModel.id)).all())
        lines = {item.id: list(db.exec(select(TransactionLineModel)
                                       .where(TransactionLineModel.transaction_id == item.id)
                                       .order_by(TransactionLineModel.line_order)).all()) for item in items}
        return [(item.description, item.transaction_date, item.is_posted,
                 [(line.account_id, line.amount) for line in lines[item.id]]) for item in items]


def test_quick_entry_page_and_link(client, logged_in):
    listing = client.get("/transactions")
    assert 'data-tooltip="Γρήγορη καταχώριση"' in listing.text
    assert 'href="/transactions/quick"' in listing.text
    page = client.get("/transactions/quick")
    assert page.status_code == 200
    assert "data-quick-form" in page.text
    assert page.text.count("data-quick-row>") == 2  # 1 row + the template
    assert 'data-tooltip="Αποθήκευση πρόχειρων"' in page.text
    assert 'data-tooltip="Οριστικοποίηση όλων"' in page.text
    assert 'name="mode" value="post"' in page.text


def test_quick_entry_saves_drafts(client, csrf, logged_in, app):
    cash_id, revenue_id = _quick_accounts(app, logged_in[1])
    response = client.post("/transactions/quick", data=_quick_payload(csrf, cash_id, revenue_id))
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/transactions")
    saved = _transactions(app)
    assert saved == [
        ("Είσπραξη Α", date(2026, 1, 15), False, [(cash_id, 10), (revenue_id, -10)]),
        ("Είσπραξη Β", date(2026, 1, 16), False, [(cash_id, 20.50), (revenue_id, -20.50)]),
    ]
    listing = client.get("/transactions")
    assert "Αποθηκεύτηκαν 2 εγγραφές." in listing.text
    assert listing.text.count("data-transaction-row") == 2


def test_quick_entry_posts_all(client, csrf, logged_in, app):
    cash_id, revenue_id = _quick_accounts(app, logged_in[1])
    response = client.post("/transactions/quick", data=_quick_payload(csrf, cash_id, revenue_id, mode=["draft", "post"]),
                           headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/transactions"
    assert [item[2] for item in _transactions(app)] == [True, True]
    assert "Οριστικοποιήθηκαν 2 εγγραφές." in client.get("/transactions").text


def test_quick_entry_is_all_or_nothing(client, csrf, logged_in, app):
    cash_id, revenue_id = _quick_accounts(app, logged_in[1])
    response = client.post("/transactions/quick", data=_quick_payload(
        csrf, cash_id, revenue_id,
        row_date=["15/01/2026", "16/01/2026", "31/02/2026", "17/01/2026", "18/01/2026"],
        row_description=["Έγκυρη γραμμή", "Ίδιος λογαριασμός", "Κακή ημερομηνία", "", "Αρνητικό ποσό"],
        row_debit=[str(cash_id), str(cash_id), str(cash_id), str(cash_id), str(cash_id)],
        row_credit=[str(revenue_id), str(cash_id), str(revenue_id), str(revenue_id), str(revenue_id)],
        row_amount=["10", "5", "5", "5", "-5"],
    ))
    assert response.status_code == 422
    assert _transactions(app) == []
    assert "Δεν αποθηκεύτηκε καμία εγγραφή." in response.text
    assert 'value="Έγκυρη γραμμή"' in response.text
    form = response.text.split("data-quick-form", 1)[1]
    assert form.count(f'value="{cash_id}" selected') == 6
    assert "ο ίδιος λογαριασμός" in response.text
    assert "Μη έγκυρη ημερομηνία." in response.text
    assert "Απαιτείται περιγραφή." in response.text
    assert "Το ποσό πρέπει να είναι θετικό." in response.text
    assert response.text.count("quick-row has-error") == 4


def test_quick_entry_rejects_empty_and_inactive(client, csrf, logged_in, app):
    cash_id, revenue_id = _quick_accounts(app, logged_in[1], inactive=True)
    empty = client.post("/transactions/quick", data={"csrf_token": csrf, "row_date": ["15/01/2026", "15/01/2026"],
                                                     "row_description": ["", ""], "row_debit": ["", ""],
                                                     "row_credit": ["", ""], "row_amount": ["", ""]})
    assert empty.status_code == 422
    assert "Δεν υπάρχουν συμπληρωμένες γραμμές." in empty.text
    inactive = client.post("/transactions/quick", data=_quick_payload(csrf, cash_id, revenue_id))
    assert inactive.status_code == 422
    assert "δεν είναι ενεργός" in inactive.text
    assert _transactions(app) == []


def test_dashboard_flow_chart_splits_pl_and_nets_transfers(client, logged_in, app):
    user_id, company_id = logged_in
    month = date.today().replace(day=1)
    day = month + timedelta(days=4)
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00.01", name="Ταμείο", account_type="asset")
        bank = AccountModel(company_id=company_id, code="38.03.01", name="Τράπεζα", account_type="asset")
        revenue = AccountModel(company_id=company_id, code="70.00.01", name="Πωλήσεις", account_type="revenue")
        expense = AccountModel(company_id=company_id, code="60.00.01", name="Αμοιβές", account_type="expense")
        db.add_all([cash, bank, revenue, expense])
        db.flush()
        entries = [
            ("Πώληση", cash, revenue, 100, True),
            ("Αμοιβή", expense, cash, 40, True),
            ("Μεταφορά", bank, cash, 30, True),
            ("Πρόχειρη πώληση", cash, revenue, 999, False),
        ]
        for description, debit, credit, amount, posted in entries:
            transaction = TransactionModel(company_id=company_id, created_by_id=user_id, transaction_date=day,
                                           description=description, is_posted=posted)
            db.add(transaction)
            db.flush()
            db.add(TransactionLineModel(transaction_id=transaction.id, account_id=debit.id, amount=amount, line_order=0))
            db.add(TransactionLineModel(transaction_id=transaction.id, account_id=credit.id, amount=-amount, line_order=1))
        db.commit()

    from app.web.routes import GREEK_MONTHS_SHORT

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert (
        f'data-month="{month:%Y-%m}" data-label="{GREEK_MONTHS_SHORT[month.month - 1]} {month.year}" '
        'data-revenue="100.00" data-expenses="40.00" data-net="60.00" data-cash-in="100.00" data-cash-out="40.00"'
    ) in dashboard.text
    assert dashboard.text.count('class="flow-month"') == 12
    assert "100,00 €" in dashboard.text
    assert "40,00 €" in dashboard.text
    assert '<span class="flow-kpi-sign">+</span><span data-countup>60,00 €</span>' in dashboard.text
    assert "flow-kpi-net is-positive" in dashboard.text
    assert "flow-empty" not in dashboard.text


def test_dashboard_stream_chart_shows_sources_targets_and_surplus(client, logged_in, app):
    user_id, company_id = logged_in
    day = date.today().replace(day=1) + timedelta(days=3)
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00", name="Ταμείο", account_type="asset")
        sales = AccountModel(company_id=company_id, code="70.00", name="Πωλήσεις", account_type="revenue")
        services = AccountModel(company_id=company_id, code="73.00", name="Υπηρεσίες", account_type="revenue")
        wages = AccountModel(company_id=company_id, code="60.00", name="Μισθοί", account_type="expense")
        rent = AccountModel(company_id=company_id, code="62.00", name="Ενοίκια", account_type="expense")
        misc = AccountModel(company_id=company_id, code="64.00", name="Διάφορα", account_type="expense")
        db.add_all([cash, sales, services, wages, rent, misc])
        db.flush()
        entries = [
            (cash, sales, 300, True), (cash, services, 100, True),
            (wages, cash, 150, True), (rent, cash, 90, True), (misc, cash, 10, True),
            (misc, cash, 500, False),
        ]
        for debit, credit, amount, posted in entries:
            transaction = TransactionModel(company_id=company_id, created_by_id=user_id, transaction_date=day,
                                           description="s", is_posted=posted)
            db.add(transaction)
            db.flush()
            db.add(TransactionLineModel(transaction_id=transaction.id, account_id=debit.id, amount=amount, line_order=0))
            db.add(TransactionLineModel(transaction_id=transaction.id, account_id=credit.id, amount=-amount, line_order=1))
        db.commit()
        wages_id, sales_id = wages.id, sales.id

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "data-stream-chart" in dashboard.text
    assert "Πού πάνε τα χρήματα" in dashboard.text
    assert (f'data-key="expense-{wages_id}" data-side="right" data-label="Μισθοί" data-amount="150.00" '
            'data-share="37.5"') in dashboard.text
    assert (f'data-key="revenue-{sales_id}" data-side="left" data-label="Πωλήσεις" data-amount="300.00" '
            'data-share="75.0"') in dashboard.text
    assert 'data-key="surplus" data-side="right" data-label="Πλεόνασμα" data-amount="150.00" data-share="37.5"' in dashboard.text
    assert dashboard.text.count('class="stream-link"') == 6
    assert "Έσοδα · 400,00 €" in dashboard.text
    assert "flow-empty" not in dashboard.text


def test_account_types_are_shown_in_greek(client, csrf, logged_in, app):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        supplier = AccountModel(company_id=company_id, code="50.00", name="Προμηθευτές", account_type="liability")
        cash = AccountModel(company_id=company_id, code="38.00", name="Ταμείο", account_type="asset")
        db.add_all([supplier, cash])
        db.flush()
        transaction = TransactionModel(company_id=company_id, created_by_id=user_id, transaction_date=date(2026, 3, 1),
                                       description="Πληρωμή", is_posted=True)
        db.add(transaction)
        db.flush()
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=supplier.id, amount=50, line_order=0))
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=cash.id, amount=-50, line_order=1))
        db.commit()
    listing = client.get("/accounts")
    assert 'class="type-pill type-liability">Υποχρεώσεις<' in listing.text
    form = client.get("/accounts/new", headers={"HX-Request": "true"})
    for english, greek in (("asset", "Ενεργητικό"), ("liability", "Υποχρεώσεις"), ("equity", "Καθαρή θέση"),
                           ("revenue", "Έσοδα"), ("expense", "Έξοδα")):
        assert f'<option value="{english}" >{greek}</option>' in form.text
    assert ">Asset<" not in form.text
    trial = client.get("/reports/result?report_type=trial_balance&as_of_date=31/12/2026", headers={"HX-Request": "true"})
    assert "Υποχρεώσεις" in trial.text
    assert ">liability<" not in trial.text


def test_olap_report_html_pdf_and_csv(client, logged_in, app):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00", name="Ταμείο", account_type="asset")
        rent = AccountModel(company_id=company_id, code="62.00", name="Ενοίκιο", account_type="expense")
        db.add_all([cash, rent])
        db.flush()
        transaction = TransactionModel(company_id=company_id, created_by_id=user_id, is_posted=True,
                                       transaction_date=date(2026, 1, 15), description="Ενοίκιο Ιανουαρίου")
        db.add(transaction)
        db.flush()
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=rent.id, amount=Decimal("500")))
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=cash.id, amount=Decimal("-500")))
        db.commit()

    query = ("report_type=olap&start_date=01/01/2026&end_date=31/01/2026&row_dim=month&row_dim=account"
             "&col_dim=account_type&measure=natural&measure=debit&chart_type=stacked")
    page = client.get("/reports")
    assert page.status_code == 200
    assert 'value="olap"' in page.text
    assert "Σχεδιασμός κύβου" in page.text

    html = client.get(f"/reports/result?{query}")
    assert html.status_code == 200
    assert "data-olap-chart" in html.text
    assert '"type": "stacked"' in html.text
    assert "62.00 · Ενοίκιο" in html.text
    assert "500,00 €" in html.text

    pdf = client.get(f"/reports/pdf?{query}")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")

    csv_response = client.get(f"/reports/olap.csv?{query}")
    assert csv_response.status_code == 200
    assert csv_response.mimetype == "text/csv"
    assert "Μήνας;Λογαριασμός;" in csv_response.text
    assert "Σύνολο;;" in csv_response.text


def test_transactions_list_filters_and_sorting(client, logged_in, app):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00", name="Ταμείο", account_type="asset")
        rent = AccountModel(company_id=company_id, code="62.00", name="Ενοίκιο", account_type="expense")
        db.add_all([cash, rent])
        db.flush()
        rows = (
            (date(2026, 1, 15), "Ενοίκιο Ιανουαρίου", Decimal("500"), True, "ΤΠΥ-1"),
            (date(2026, 2, 3), "Λογαριασμός ΔΕΗ", Decimal("120"), False, None),
            (date(2025, 12, 30), "Αγορά αναλωσίμων", Decimal("45.50"), True, None),
            (date(2025, 12, 29), "«ΆΛΦΑ» τιμολόγιο", Decimal("10"), True, None),
        )
        for when, description, amount, posted, reference in rows:
            transaction = TransactionModel(company_id=company_id, created_by_id=user_id, is_posted=posted,
                                           transaction_date=when, description=description, reference=reference)
            db.add(transaction)
            db.flush()
            db.add(TransactionLineModel(transaction_id=transaction.id, account_id=rent.id, amount=amount))
            db.add(TransactionLineModel(transaction_id=transaction.id, account_id=cash.id, amount=-amount))
        db.commit()

    def titles(url):
        page = client.get(url)
        assert page.status_code == 200
        return re.findall(r"<td data-label=\"Περιγραφή\"><strong>(.*?)</strong>", page.text)

    assert titles("/transactions") == ["Λογαριασμός ΔΕΗ", "Ενοίκιο Ιανουαρίου", "Αγορά αναλωσίμων", "«ΆΛΦΑ» τιμολόγιο"]
    assert titles("/transactions?sort=date&dir=asc")[0] == "«ΆΛΦΑ» τιμολόγιο"
    assert titles("/transactions?sort=amount&dir=desc")[:2] == ["Ενοίκιο Ιανουαρίου", "Λογαριασμός ΔΕΗ"]
    # Greek collation: accents, case and punctuation are ignored, so «ΆΛΦΑ» sorts as "αλφα" (after "αγορα").
    assert titles("/transactions?sort=description&dir=asc") == [
        "Αγορά αναλωσίμων", "«ΆΛΦΑ» τιμολόγιο", "Ενοίκιο Ιανουαρίου", "Λογαριασμός ΔΕΗ"]
    assert titles("/transactions?sort=status&dir=asc")[0] == "Λογαριασμός ΔΕΗ"  # drafts first

    assert titles("/transactions?date=2026") == ["Λογαριασμός ΔΕΗ", "Ενοίκιο Ιανουαρίου"]
    assert titles("/transactions?date=2026-01") == ["Ενοίκιο Ιανουαρίου"]
    assert titles("/transactions?date=02/2026") == ["Λογαριασμός ΔΕΗ"]
    assert titles("/transactions?date=30/12/2025") == ["Αγορά αναλωσίμων"]
    assert titles("/transactions?q=αλφα") == ["«ΆΛΦΑ» τιμολόγιο"]      # accent- and case-insensitive
    assert titles("/transactions?q=ενοικιο ιανουαριου") == ["Ενοίκιο Ιανουαρίου"]
    assert titles("/transactions?q=δεη") == ["Λογαριασμός ΔΕΗ"]
    assert titles("/transactions?q=ΤΠΥ") == ["Ενοίκιο Ιανουαρίου"]
    assert titles("/transactions?min=100&max=200") == ["Λογαριασμός ΔΕΗ"]
    assert titles("/transactions?min=45,50") == ["Λογαριασμός ΔΕΗ", "Ενοίκιο Ιανουαρίου", "Αγορά αναλωσίμων"]
    assert titles("/transactions?max=45,5") == ["Αγορά αναλωσίμων", "«ΆΛΦΑ» τιμολόγιο"]
    assert titles("/transactions?status=draft") == ["Λογαριασμός ΔΕΗ"]
    assert titles("/transactions?status=posted&sort=amount&dir=asc") == ["«ΆΛΦΑ» τιμολόγιο", "Αγορά αναλωσίμων", "Ενοίκιο Ιανουαρίου"]
    assert titles("/transactions?q=nothing-here") == []
    assert "Καμία εγγραφή δεν ταιριάζει" in client.get("/transactions?q=nothing-here").text
    page = client.get("/transactions?status=draft&sort=amount&dir=asc")
    assert 'name="next" value="/transactions?status=draft&amp;sort=amount&amp;dir=asc"' in page.text


def test_editing_a_transaction_returns_to_the_filtered_list(client, csrf, logged_in, app):
    user_id, company_id = logged_in
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00", name="Ταμείο", account_type="asset")
        rent = AccountModel(company_id=company_id, code="62.00", name="Ενοίκιο", account_type="expense")
        db.add_all([cash, rent])
        db.flush()
        transaction = TransactionModel(company_id=company_id, created_by_id=user_id, is_posted=False,
                                       transaction_date=date(2026, 1, 15), description="Πρόχειρη")
        db.add(transaction)
        db.flush()
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=rent.id, amount=Decimal("50")))
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=cash.id, amount=Decimal("-50")))
        db.commit()
        transaction_id, rent_id, cash_id = transaction.id, rent.id, cash.id

    listing = "/transactions?status=draft&sort=amount&dir=asc"
    page = client.get(listing)
    assert (f'data-modal-url="/transactions/{transaction_id}/edit?next=/transactions?status%3Ddraft%26sort%3Damount%26dir%3Dasc"'
            in page.text)

    form = client.get(f"/transactions/{transaction_id}/edit?next={quote(listing, safe='')}")
    assert f'name="next" value="{listing.replace("&", "&amp;")}"' in form.text

    response = client.post(f"/transactions/{transaction_id}/edit", headers={"HX-Request": "true"}, data={
        "csrf_token": csrf, "next": listing, "transaction_date": "15/01/2026", "description": "Αλλαγμένη",
        "account_id": [str(rent_id), str(cash_id)], "amount": ["60", "-60"], "line_description": ["", ""],
    })
    assert response.status_code == 200, response.text[:300]
    assert response.headers["HX-Redirect"] == listing

    # An off-site "next" is ignored.
    response = client.post(f"/transactions/{transaction_id}/edit", headers={"HX-Request": "true"}, data={
        "csrf_token": csrf, "next": "https://evil.example/x", "transaction_date": "15/01/2026",
        "description": "Αλλαγμένη", "account_id": [str(rent_id), str(cash_id)], "amount": ["60", "-60"],
        "line_description": ["", ""],
    })
    assert response.headers["HX-Redirect"] == "/transactions"
