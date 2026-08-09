"""HTML routes for the complete accounting application."""

import csv
import io
import shutil
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from sqlalchemy.orm import selectinload
from sqlmodel import col, func, select

from app.core.security import hash_password, verify_password
from app.domain.types import AccountType
from app.extensions import get_db, reset_engine
from app.infrastructure.database.models import (
    AccountModel,
    CompanyModel,
    TransactionLineModel,
    TransactionModel,
    UserCompanyAccessModel,
    UserModel,
)
from app.web import reports
from app.web.auth import company_required, login_required, superuser_required
from app.web.pdf_reports import build_report_pdf

web = Blueprint("web", __name__)
ACCOUNT_TYPES = list(AccountType)
ROLES = ["owner", "admin", "accountant", "viewer"]
PAGE_SIZE = 25


def finish(endpoint: str, **values):
    target = url_for(endpoint, **values)
    if request.headers.get("HX-Request"):
        response = make_response("")
        response.headers["HX-Redirect"] = target
        return response
    return redirect(target)


def parse_date(value: str | None, fallback: date | None = None) -> date:
    raw_value = (value or "").strip()
    for parser in (
        lambda raw: datetime.strptime(raw, "%d/%m/%Y").date(),
        date.fromisoformat,
    ):
        try:
            return parser(raw_value)
        except ValueError:
            continue
    if fallback is not None:
        return fallback
    raise ValueError(f"Invalid date: {raw_value}")


def companies_for_user(user_id: int):
    db = get_db()
    statement = (
        select(CompanyModel)
        .join(UserCompanyAccessModel, UserCompanyAccessModel.company_id == CompanyModel.id)
        .where(UserCompanyAccessModel.user_id == user_id, CompanyModel.is_active == True)  # noqa: E712
        .order_by(CompanyModel.name)
    )
    return list(db.exec(statement).all())


@web.app_context_processor
def shared_template_context():
    companies = companies_for_user(g.user.id) if getattr(g, "user", None) else []
    return {
        "companies": companies,
        "account_types": ACCOUNT_TYPES,
        "roles": ROLES,
        "today": date.today(),
    }


@web.app_template_filter("money")
def money(value, currency=None):
    amount = Decimal(value or 0)
    code = currency or (g.company.currency if getattr(g, "company", None) else "EUR")
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    symbol = "€" if code.upper() == "EUR" else code
    return f"{formatted} {symbol}"


@web.app_template_filter("dategr")
def dategr(value):
    return value.strftime("%d/%m/%Y") if value else "-"


@web.app_template_filter("filesize")
def filesize(value):
    size = float(value)
    for unit in ("Bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "Bytes" else f"{size:.2f} {unit}"
        size /= 1024


@web.app_template_filter("abs")
def absolute(value):
    return abs(value)


@web.get("/login")
def login():
    return render_template("auth/login.html")


@web.post("/login")
def login_post():
    db = get_db()
    email = request.form.get("email", "").strip().lower()
    user = db.exec(select(UserModel).where(UserModel.email == email)).first()
    if not user or not verify_password(request.form.get("password", ""), user.hashed_password):
        flash("Λανθασμένο email ή κωδικός.", "error")
        return render_template("auth/login.html", email=email), 401
    if not user.is_active:
        flash("Ο λογαριασμός χρήστη είναι ανενεργός.", "error")
        return render_template("auth/login.html", email=email), 401
    access = db.exec(
        select(UserCompanyAccessModel).where(
            UserCompanyAccessModel.user_id == user.id,
            UserCompanyAccessModel.is_default == True,  # noqa: E712
        )
    ).first()
    token = session.get("csrf_token")
    session.clear()
    session["csrf_token"] = token
    session["user_id"] = user.id
    if access:
        company = db.get(CompanyModel, access.company_id)
        if company and company.is_active:
            session["company_id"] = company.id
    flash("Καλώς ήρθατε.", "success")
    return finish("web.dashboard")


@web.get("/register")
def register():
    return render_template("auth/register.html")


@web.post("/register")
def register_post():
    db = get_db()
    email = request.form.get("email", "").strip().lower()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    company_name = request.form.get("company_name", "").strip()
    if not email or not full_name or len(password) < 6:
        flash("Συμπληρώστε τα υποχρεωτικά πεδία. Ο κωδικός χρειάζεται 6 χαρακτήρες.", "error")
        return render_template("auth/register.html"), 422
    if db.exec(select(UserModel).where(UserModel.email == email)).first():
        flash("Υπάρχει ήδη χρήστης με αυτό το email.", "error")
        return render_template("auth/register.html"), 409
    user_count = db.exec(select(func.count()).select_from(UserModel)).one()
    user = UserModel(email=email, full_name=full_name, hashed_password=hash_password(password),
                     is_superuser=user_count == 0)
    db.add(user)
    db.flush()
    if company_name:
        prefix = "".join(ch for ch in company_name.upper() if ch.isalnum())[:3].ljust(3, "X")
        company = CompanyModel(name=company_name, code=f"{prefix}-{uuid.uuid4().hex[:5].upper()}")
        db.add(company)
        db.flush()
        db.add(UserCompanyAccessModel(user_id=user.id, company_id=company.id, role="admin", is_default=True))
        session["company_id"] = company.id
    db.commit()
    session["user_id"] = user.id
    flash("Ο λογαριασμός δημιουργήθηκε.", "success")
    return finish("web.dashboard")


@web.post("/logout")
@login_required
def logout():
    session.clear()
    return finish("web.login")


@web.post("/companies/switch")
@login_required
def switch_company():
    company_id = request.form.get("company_id", type=int)
    access = get_db().exec(
        select(UserCompanyAccessModel).where(
            UserCompanyAccessModel.user_id == g.user.id,
            UserCompanyAccessModel.company_id == company_id,
        )
    ).first()
    company = get_db().get(CompanyModel, company_id) if access else None
    if not company or not company.is_active:
        flash("Δεν έχετε πρόσβαση σε αυτή την εταιρεία.", "error")
    else:
        session["company_id"] = company.id
        flash(f"Ενεργή εταιρεία: {company.name}", "success")
    return finish("web.dashboard")


@web.get("/")
@login_required
def dashboard():
    if not g.company:
        return render_template("dashboard/index.html", stats=None, accounts=[], transactions=[])
    db = get_db()
    accounts = list(db.exec(select(AccountModel).where(AccountModel.company_id == g.company.id)
                            .order_by(AccountModel.code).limit(8)).all())
    transactions = list(db.exec(select(TransactionModel).where(TransactionModel.company_id == g.company.id)
                                .order_by(col(TransactionModel.transaction_date).desc()).limit(5)).all())
    balance = reports.trial_balance(db, g.company.id, date.today())
    stats = {}
    for kind in (AccountType.ASSET, AccountType.LIABILITY, AccountType.REVENUE, AccountType.EXPENSE):
        values = [x.balance for x in balance["accounts"] if x.account.account_type == kind]
        stats[kind.value] = sum((abs(x) if kind in {AccountType.LIABILITY, AccountType.REVENUE} else x for x in values), Decimal("0"))
    return render_template("dashboard/index.html", stats=stats, accounts=accounts, transactions=transactions)


# Companies and access
@web.get("/companies")
@login_required
def companies_index():
    db = get_db()
    items = list(db.exec(select(CompanyModel).order_by(CompanyModel.name)).all()) if g.user.is_superuser else list(
        db.exec(select(CompanyModel).where(CompanyModel.is_active == True).order_by(CompanyModel.name)).all()  # noqa: E712
    )
    return render_template("companies/index.html", items=items)


@web.route("/companies/new", methods=["GET", "POST"])
@login_required
def company_new():
    if request.method == "GET":
        return render_template("companies/form.html", company=None)
    db = get_db()
    name, code = request.form.get("name", "").strip(), request.form.get("code", "").strip().upper()
    if not name or not code:
        flash("Συμπληρώστε όνομα και κωδικό εταιρείας.", "error")
        return render_template("companies/form.html", company=None), 422
    if db.exec(select(CompanyModel).where(CompanyModel.code == code)).first():
        flash("Ο κωδικός εταιρείας χρησιμοποιείται ήδη.", "error")
        return render_template("companies/form.html", company=None), 409
    company = CompanyModel(name=name, code=code,
                           fiscal_year_start_month=request.form.get("fiscal_year_start_month", 1, type=int),
                           currency=request.form.get("currency", "EUR").strip().upper())
    db.add(company)
    db.flush()
    db.add(UserCompanyAccessModel(user_id=g.user.id, company_id=company.id, role="owner", is_default=True))
    db.exec(select(UserCompanyAccessModel).where(UserCompanyAccessModel.user_id == g.user.id,
                                                 UserCompanyAccessModel.company_id != company.id)).all()
    db.commit()
    session["company_id"] = company.id
    flash("Η εταιρεία δημιουργήθηκε.", "success")
    return finish("web.companies_index")


@web.route("/companies/<int:company_id>/edit", methods=["GET", "POST"])
@login_required
def company_edit(company_id):
    db, company = get_db(), get_db().get(CompanyModel, company_id)
    if not company:
        abort(404)
    if request.method == "GET":
        return render_template("companies/form.html", company=company)
    company.name = request.form.get("name", company.name).strip()
    company.code = request.form.get("code", company.code).strip().upper()
    company.currency = request.form.get("currency", company.currency).strip().upper()
    company.fiscal_year_start_month = request.form.get("fiscal_year_start_month", company.fiscal_year_start_month, type=int)
    company.is_active = "is_active" in request.form
    company.updated_at = datetime.now(timezone.utc)
    db.add(company)
    db.commit()
    flash("Η εταιρεία ενημερώθηκε.", "success")
    return finish("web.companies_index")


@web.post("/companies/<int:company_id>/delete")
@superuser_required
def company_delete(company_id):
    company = get_db().get(CompanyModel, company_id)
    if not company:
        abort(404)
    get_db().delete(company)
    get_db().commit()
    if session.get("company_id") == company_id:
        session.pop("company_id", None)
    flash("Η εταιρεία διαγράφηκε.", "success")
    return finish("web.companies_index")


@web.get("/companies/<int:company_id>/access")
@login_required
def company_access(company_id):
    company = get_db().get(CompanyModel, company_id)
    if not company:
        abort(404)
    access = list(get_db().exec(select(UserCompanyAccessModel).where(
        UserCompanyAccessModel.company_id == company_id).options(selectinload(UserCompanyAccessModel.user))).all())
    users = list(get_db().exec(select(UserModel).order_by(UserModel.full_name)).all())
    return render_template("companies/access.html", company=company, access=access, users=users)


@web.post("/companies/<int:company_id>/access")
@login_required
def company_access_add(company_id):
    db = get_db()
    user_id = request.form.get("user_id", type=int)
    role = request.form.get("role", "viewer")
    item = db.exec(select(UserCompanyAccessModel).where(UserCompanyAccessModel.company_id == company_id,
                                                        UserCompanyAccessModel.user_id == user_id)).first()
    if item:
        item.role = role
    else:
        item = UserCompanyAccessModel(company_id=company_id, user_id=user_id, role=role)
    db.add(item)
    db.commit()
    flash("Η πρόσβαση ενημερώθηκε.", "success")
    return finish("web.company_access", company_id=company_id)


@web.post("/companies/<int:company_id>/access/<int:user_id>/delete")
@login_required
def company_access_delete(company_id, user_id):
    item = get_db().exec(select(UserCompanyAccessModel).where(UserCompanyAccessModel.company_id == company_id,
                                                              UserCompanyAccessModel.user_id == user_id)).first()
    if not item:
        abort(404)
    get_db().delete(item)
    get_db().commit()
    flash("Η πρόσβαση αφαιρέθηκε.", "success")
    return finish("web.company_access", company_id=company_id)


# Users
@web.get("/users")
@login_required
def users_index():
    users = list(get_db().exec(select(UserModel).order_by(UserModel.full_name)).all())
    return render_template("users/index.html", users=users)


@web.route("/users/new", methods=["GET", "POST"])
@login_required
def user_new():
    if request.method == "GET":
        return render_template("users/form.html", user=None)
    email, password = request.form.get("email", "").strip().lower(), request.form.get("password", "")
    if len(password) < 8 or not email:
        flash("Απαιτείται email και κωδικός τουλάχιστον 8 χαρακτήρων.", "error")
        return render_template("users/form.html", user=None), 422
    if get_db().exec(select(UserModel).where(UserModel.email == email)).first():
        flash("Το email χρησιμοποιείται ήδη.", "error")
        return render_template("users/form.html", user=None), 409
    user = UserModel(email=email, full_name=request.form.get("full_name", "").strip(),
                     hashed_password=hash_password(password), is_superuser="is_superuser" in request.form)
    get_db().add(user)
    get_db().commit()
    flash("Ο χρήστης δημιουργήθηκε.", "success")
    return finish("web.users_index")


@web.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def user_edit(user_id):
    user = get_db().get(UserModel, user_id)
    if not user:
        abort(404)
    if user.id != g.user.id and not g.user.is_superuser:
        abort(403)
    if request.method == "GET":
        return render_template("users/form.html", user=user)
    user.email = request.form.get("email", user.email).strip().lower()
    user.full_name = request.form.get("full_name", user.full_name).strip()
    user.is_active = "is_active" in request.form
    if g.user.is_superuser:
        user.is_superuser = "is_superuser" in request.form
    user.updated_at = datetime.now(timezone.utc)
    get_db().add(user)
    get_db().commit()
    flash("Ο χρήστης ενημερώθηκε.", "success")
    return finish("web.users_index")


@web.post("/users/<int:user_id>/delete")
@superuser_required
def user_delete(user_id):
    user = get_db().get(UserModel, user_id)
    if not user:
        abort(404)
    get_db().delete(user)
    get_db().commit()
    flash("Ο χρήστης διαγράφηκε.", "success")
    return finish("web.users_index")


@web.route("/profile/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "GET":
        return render_template("users/password.html")
    if not verify_password(request.form.get("current_password", ""), g.user.hashed_password):
        flash("Ο τρέχων κωδικός δεν είναι σωστός.", "error")
        return render_template("users/password.html"), 400
    password = request.form.get("new_password", "")
    if len(password) < 8:
        flash("Ο νέος κωδικός χρειάζεται τουλάχιστον 8 χαρακτήρες.", "error")
        return render_template("users/password.html"), 422
    g.user.hashed_password = hash_password(password)
    get_db().add(g.user)
    get_db().commit()
    flash("Ο κωδικός άλλαξε.", "success")
    return finish("web.dashboard")


# Accounts
@web.get("/accounts")
@company_required
def accounts_index():
    db = get_db()
    total = db.exec(
        select(func.count()).select_from(AccountModel).where(AccountModel.company_id == g.company.id)
    ).one()
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, pages)
    accounts = list(
        db.exec(
            select(AccountModel)
            .where(AccountModel.company_id == g.company.id)
            .order_by(AccountModel.code)
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        ).all()
    )
    account_ids = [account.id for account in accounts]
    balances = {}
    used_account_ids = set()
    if account_ids:
        balance_rows = db.exec(
            select(
                TransactionLineModel.account_id,
                func.coalesce(func.sum(TransactionLineModel.amount), 0),
            )
            .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
            .where(
                TransactionModel.company_id == g.company.id,
                TransactionModel.is_posted == True,  # noqa: E712
                col(TransactionLineModel.account_id).in_(account_ids),
            )
            .group_by(TransactionLineModel.account_id)
        ).all()
        balances = {account_id: balance for account_id, balance in balance_rows}
        used_account_ids = set(
            db.exec(
                select(TransactionLineModel.account_id)
                .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
                .where(
                    TransactionModel.company_id == g.company.id,
                    col(TransactionLineModel.account_id).in_(account_ids),
                )
                .distinct()
            ).all()
        )
    pagination = {"page": page, "pages": pages, "total": total}
    return render_template(
        "accounts/index.html",
        accounts=accounts,
        balances=balances,
        used_account_ids=used_account_ids,
        pagination=pagination,
    )


@web.get("/accounts/<int:account_id>/ledger")
@company_required
def account_ledger(account_id):
    data = get_account_ledger_data(account_id, request.args.get("page", 1, type=int))
    if not data:
        abort(404)
    return render_template("accounts/ledger.html", **data)


def get_account_ledger_data(
    account_id: int, requested_page: int | None = 1, page_size: int | None = PAGE_SIZE
):
    db = get_db()
    account = db.exec(
        select(AccountModel).where(
            AccountModel.id == account_id,
            AccountModel.company_id == g.company.id,
        )
    ).first()
    if not account:
        return None

    filters = (
        TransactionModel.company_id == g.company.id,
        TransactionModel.is_posted == True,  # noqa: E712
        TransactionLineModel.account_id == account.id,
    )
    total = db.exec(
        select(func.count())
        .select_from(TransactionLineModel)
        .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
        .where(*filters)
    ).one()
    page = max(requested_page or 1, 1)
    pages = max((total + page_size - 1) // page_size, 1) if page_size else 1
    page = min(page, pages)

    chronological_order = (
        TransactionModel.transaction_date,
        TransactionModel.id,
        TransactionLineModel.line_order,
        TransactionLineModel.id,
    )
    running_balance = func.sum(TransactionLineModel.amount).over(
        order_by=chronological_order
    ).label("running_balance")
    statement = (
        select(TransactionLineModel, TransactionModel, running_balance)
        .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
        .where(*filters)
        .order_by(
            col(TransactionModel.transaction_date).desc(),
            col(TransactionModel.id).desc(),
            col(TransactionLineModel.line_order).desc(),
            col(TransactionLineModel.id).desc(),
        )
    )
    if page_size:
        statement = statement.offset((page - 1) * page_size).limit(page_size)
    entries = [
        {"line": line, "transaction": transaction, "balance": balance}
        for line, transaction, balance in db.exec(statement).all()
    ]
    current_balance = db.exec(
        select(func.coalesce(func.sum(TransactionLineModel.amount), 0))
        .select_from(TransactionLineModel)
        .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
        .where(*filters)
    ).one()
    pagination = {"page": page, "pages": pages, "total": total}
    return {
        "account": account,
        "entries": entries,
        "current_balance": current_balance,
        "pagination": pagination,
    }


@web.route("/accounts/new", methods=["GET", "POST"])
@company_required
def account_new():
    accounts = list(get_db().exec(select(AccountModel).where(AccountModel.company_id == g.company.id)
                                  .order_by(AccountModel.code)).all())
    if request.method == "GET":
        return render_template("accounts/form.html", account=None, accounts=accounts)
    return save_account(None, accounts)


@web.route("/accounts/<int:account_id>/edit", methods=["GET", "POST"])
@company_required
def account_edit(account_id):
    account = get_db().exec(select(AccountModel).where(AccountModel.id == account_id,
                                                        AccountModel.company_id == g.company.id)).first()
    if not account:
        abort(404)
    accounts = list(get_db().exec(select(AccountModel).where(AccountModel.company_id == g.company.id)
                                  .order_by(AccountModel.code)).all())
    if request.method == "GET":
        return render_template("accounts/form.html", account=account, accounts=accounts)
    return save_account(account, accounts)


def save_account(account, accounts):
    db = get_db()
    code = request.form.get("code", "").strip()
    duplicate = db.exec(select(AccountModel).where(AccountModel.company_id == g.company.id,
                                                    AccountModel.code == code)).first()
    if duplicate and (account is None or duplicate.id != account.id):
        flash("Υπάρχει ήδη λογαριασμός με αυτόν τον κωδικό.", "error")
        return render_template("accounts/form.html", account=account, accounts=accounts), 409
    try:
        kind = AccountType(request.form.get("account_type", ""))
    except ValueError:
        flash("Επιλέξτε έγκυρο τύπο λογαριασμού.", "error")
        return render_template("accounts/form.html", account=account, accounts=accounts), 422
    parent_id = request.form.get("parent_id", type=int)
    if account is None:
        account = AccountModel(company_id=g.company.id, code=code,
                               name=request.form.get("name", "").strip(), account_type=kind)
    account.code, account.name, account.account_type = code, request.form.get("name", "").strip(), kind
    account.parent_id = parent_id or None
    account.description = request.form.get("description", "").strip() or None
    account.is_active = "is_active" in request.form if request.form.get("editing") else True
    account.updated_at = datetime.now(timezone.utc)
    db.add(account)
    db.commit()
    flash("Ο λογαριασμός αποθηκεύτηκε.", "success")
    return finish("web.accounts_index")


@web.post("/accounts/<int:account_id>/delete")
@company_required
def account_delete(account_id):
    account = get_db().exec(select(AccountModel).where(AccountModel.id == account_id,
                                                        AccountModel.company_id == g.company.id)).first()
    if not account:
        abort(404)
    has_movements = get_db().exec(
        select(TransactionLineModel.id)
        .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
        .where(
            TransactionModel.company_id == g.company.id,
            TransactionLineModel.account_id == account_id,
        )
        .limit(1)
    ).first()
    if has_movements is not None:
        flash("Ο λογαριασμός έχει κινήσεις και δεν μπορεί να διαγραφεί.", "error")
        return finish("web.accounts_index")
    get_db().delete(account)
    get_db().commit()
    flash("Ο λογαριασμός διαγράφηκε.", "success")
    return finish("web.accounts_index")


@web.get("/accounts/export")
@company_required
def accounts_export():
    accounts = list(get_db().exec(select(AccountModel).where(AccountModel.company_id == g.company.id)
                                  .order_by(AccountModel.code)).all())
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_ALL)
    output.write("code,name,account_type\n")
    for account in accounts:
        writer.writerow([account.code, account.name, account.account_type.value])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=chart_of_accounts.csv"})


@web.post("/accounts/import")
@company_required
def accounts_import():
    uploaded = request.files.get("file")
    if not uploaded:
        flash("Επιλέξτε αρχείο CSV.", "error")
        return finish("web.accounts_index")
    lines = [line for line in uploaded.read().decode("utf-8-sig").splitlines() if line.strip()]
    if lines and "code" in lines[0].lower():
        lines = lines[1:]
    created, errors = 0, []
    for number, line in enumerate(lines, start=2):
        values = [value.strip().strip('"') for value in line.split(",")]
        if len(values) < 3:
            errors.append(f"Γραμμή {number}: Απαιτούνται 3 στήλες")
            continue
        code, name, raw_type = values[:3]
        try:
            kind = AccountType(raw_type.lower())
        except ValueError:
            errors.append(f'Γραμμή {number}: Μη έγκυρος τύπος "{raw_type}"')
            continue
        if get_db().exec(select(AccountModel).where(AccountModel.company_id == g.company.id,
                                                     AccountModel.code == code)).first():
            errors.append(f"Account with code '{code}' already exists")
            continue
        get_db().add(AccountModel(company_id=g.company.id, code=code, name=name, account_type=kind))
        get_db().flush()
        created += 1
    get_db().commit()
    flash(f"Δημιουργήθηκαν {created} λογαριασμοί.", "success")
    for error in errors[:5]:
        flash(error, "error")
    if len(errors) > 5:
        flash(f"...και {len(errors) - 5} ακόμα σφάλματα", "error")
    return finish("web.accounts_index")


# Transactions
def transaction_query(transaction_id=None):
    statement = select(TransactionModel).where(TransactionModel.company_id == g.company.id).options(
        selectinload(TransactionModel.lines)
    )
    if transaction_id is not None:
        statement = statement.where(TransactionModel.id == transaction_id)
    return statement


@web.get("/transactions")
@company_required
def transactions_index():
    db = get_db()
    total = db.exec(
        select(func.count()).select_from(TransactionModel).where(TransactionModel.company_id == g.company.id)
    ).one()
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, pages)
    transactions = list(
        db.exec(
            transaction_query()
            .order_by(col(TransactionModel.transaction_date).desc(), col(TransactionModel.id).desc())
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        ).all()
    )
    accounts = list(db.exec(select(AccountModel).where(AccountModel.company_id == g.company.id)).all())
    pagination = {"page": page, "pages": pages, "total": total}
    return render_template("transactions/index.html", transactions=transactions,
                           account_map={a.id: a for a in accounts}, pagination=pagination)


@web.route("/transactions/new", methods=["GET", "POST"])
@company_required
def transaction_new():
    accounts = active_accounts()
    if request.method == "GET":
        return render_template("transactions/form.html", transaction=None, accounts=accounts,
                               form_lines=[{}, {}], copy=False)
    return save_transaction(None, accounts)


@web.route("/transactions/<int:transaction_id>/edit", methods=["GET", "POST"])
@company_required
def transaction_edit(transaction_id):
    transaction = get_db().exec(transaction_query(transaction_id)).first()
    if not transaction:
        abort(404)
    if transaction.is_posted:
        flash("Οι οριστικοποιημένες εγγραφές δεν αλλάζουν.", "error")
        return finish("web.transactions_index")
    accounts = active_accounts()
    if request.method == "GET":
        return render_template("transactions/form.html", transaction=transaction, accounts=accounts,
                               form_lines=transaction.lines, copy=False)
    return save_transaction(transaction, accounts)


@web.get("/transactions/<int:transaction_id>/copy")
@company_required
def transaction_copy(transaction_id):
    transaction = get_db().exec(transaction_query(transaction_id)).first()
    if not transaction:
        abort(404)
    return render_template("transactions/form.html", transaction=transaction, accounts=active_accounts(),
                           form_lines=transaction.lines, copy=True)


def active_accounts():
    return list(get_db().exec(select(AccountModel).where(AccountModel.company_id == g.company.id,
                                                          AccountModel.is_active == True)  # noqa: E712
                              .order_by(AccountModel.code)).all())


def save_transaction(transaction, accounts):
    db = get_db()
    account_ids = request.form.getlist("account_id")
    amounts = request.form.getlist("amount")
    descriptions = request.form.getlist("line_description")
    if len(account_ids) < 2:
        flash("Απαιτούνται τουλάχιστον 2 γραμμές.", "error")
        return render_template("transactions/form.html", transaction=transaction, accounts=accounts,
                               form_lines=[], copy=False), 422
    parsed = []
    try:
        for index, raw_account in enumerate(account_ids):
            account_id = int(raw_account)
            amount = Decimal(amounts[index])
            if not any(a.id == account_id for a in accounts):
                raise ValueError("Ο λογαριασμός δεν είναι ενεργός.")
            parsed.append((account_id, amount, descriptions[index] or None if index < len(descriptions) else None))
    except (ValueError, InvalidOperation, IndexError) as error:
        flash(f"Μη έγκυρη γραμμή εγγραφής: {error}", "error")
        return render_template("transactions/form.html", transaction=transaction, accounts=accounts,
                               form_lines=[], copy=False), 422
    total = sum((item[1] for item in parsed), Decimal("0"))
    if total != 0:
        flash(f"Η εγγραφή δεν ισοσκελίζεται. Διαφορά: {total}", "error")
        return render_template("transactions/form.html", transaction=transaction, accounts=accounts,
                               form_lines=[], copy=False), 422
    if transaction is None or request.form.get("copy") == "1":
        transaction = TransactionModel(company_id=g.company.id, created_by_id=g.user.id,
                                       transaction_date=date.today(), description="")
        db.add(transaction)
        db.flush()
    else:
        for line in list(transaction.lines):
            db.delete(line)
        db.flush()
    transaction.transaction_date = parse_date(request.form.get("transaction_date"))
    transaction.description = request.form.get("description", "").strip()
    transaction.reference = request.form.get("reference", "").strip() or None
    transaction.updated_at = datetime.now(timezone.utc)
    db.add(transaction)
    db.flush()
    for index, (account_id, amount, description) in enumerate(parsed):
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=account_id,
                                    amount=amount, description=description, line_order=index))
    db.commit()
    flash("Η εγγραφή αποθηκεύτηκε.", "success")
    return finish("web.transactions_index")


@web.get("/transactions/<int:transaction_id>")
@company_required
def transaction_view(transaction_id):
    transaction = get_db().exec(transaction_query(transaction_id)).first()
    if not transaction:
        abort(404)
    accounts = list(get_db().exec(select(AccountModel).where(AccountModel.company_id == g.company.id)).all())
    return render_template("transactions/detail.html", transaction=transaction,
                           account_map={a.id: a for a in accounts})


@web.post("/transactions/<int:transaction_id>/post")
@company_required
def transaction_post(transaction_id):
    transaction = get_db().exec(transaction_query(transaction_id)).first()
    if not transaction or transaction.is_posted:
        abort(404 if not transaction else 400)
    transaction.is_posted = True
    get_db().add(transaction)
    get_db().commit()
    flash("Η εγγραφή οριστικοποιήθηκε.", "success")
    return finish("web.transactions_index")


@web.post("/transactions/<int:transaction_id>/unpost")
@company_required
def transaction_unpost(transaction_id):
    transaction = get_db().exec(transaction_query(transaction_id)).first()
    if not transaction or not transaction.is_posted:
        abort(404 if not transaction else 400)
    transaction.is_posted = False
    get_db().add(transaction)
    get_db().commit()
    flash("Η εγγραφή έγινε πρόχειρη.", "success")
    return finish("web.transactions_index")


@web.post("/transactions/<int:transaction_id>/delete")
@company_required
def transaction_delete(transaction_id):
    transaction = get_db().exec(transaction_query(transaction_id)).first()
    if not transaction:
        abort(404)
    if transaction.is_posted:
        abort(400)
    get_db().delete(transaction)
    get_db().commit()
    flash("Η εγγραφή διαγράφηκε.", "success")
    return finish("web.transactions_index")


# Reports
@web.get("/reports")
@company_required
def reports_index():
    end = date.today()
    return render_template("reports/index.html", start_date=end - timedelta(days=30), end_date=end,
                           accounts=active_accounts())


@web.get("/reports/result")
@company_required
def report_result():
    kind = request.args.get("report_type", "trial_balance")
    if kind == "general_ledger":
        account_id = request.args.get("account_id", type=int)
        data = get_account_ledger_data(account_id, request.args.get("page", 1, type=int))
        if not data:
            return '<div class="empty-state">Επιλέξτε λογαριασμό.</div>'
        return render_template("reports/general_ledger.html", **data, report_type=kind)

    if kind in {"trial_balance", "balance_sheet"}:
        end = parse_date(request.args.get("as_of_date"), date.today())
    else:
        end = parse_date(request.args.get("end_date"), date.today())
    start = parse_date(request.args.get("start_date"), end - timedelta(days=30))
    db = get_db()
    if kind == "trial_balance":
        data = reports.trial_balance(db, g.company.id, end, include_summaries=True)
    elif kind == "balance_sheet":
        data = reports.balance_sheet(db, g.company.id, end)
    elif kind == "income_statement":
        data = reports.income_statement(db, g.company.id, start, end)
    elif kind == "journal":
        data = reports.journal(
            db,
            g.company.id,
            start,
            end,
            requested_page=request.args.get("page", 1, type=int),
            page_size=PAGE_SIZE,
        )
    else:
        abort(400)
    return render_template(f"reports/{kind}.html", report=data, report_type=kind)


@web.get("/reports/pdf")
@company_required
def report_pdf():
    kind = request.args.get("report_type", "trial_balance")
    if kind == "general_ledger":
        data = get_account_ledger_data(
            request.args.get("account_id", type=int), requested_page=1, page_size=None
        )
        if not data:
            abort(400, "Επιλέξτε λογαριασμό.")
    else:
        if kind in {"trial_balance", "balance_sheet"}:
            end = parse_date(request.args.get("as_of_date"), date.today())
        else:
            end = parse_date(request.args.get("end_date"), date.today())
        start = parse_date(request.args.get("start_date"), end - timedelta(days=30))
        db = get_db()
        if kind == "trial_balance":
            data = reports.trial_balance(db, g.company.id, end, include_summaries=True)
        elif kind == "balance_sheet":
            data = reports.balance_sheet(db, g.company.id, end)
        elif kind == "income_statement":
            data = reports.income_statement(db, g.company.id, start, end)
        elif kind == "journal":
            data = reports.journal(db, g.company.id, start, end)
        else:
            abort(400, "Άγνωστος τύπος αναφοράς.")

    content, filename = build_report_pdf(kind, data, g.company)
    return send_file(
        io.BytesIO(content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


# Backups
def database_path():
    url = current_app.config["DATABASE_URL"]
    if not url.startswith("sqlite"):
        raise RuntimeError("Τα αντίγραφα ασφαλείας υποστηρίζουν μόνο SQLite.")
    return Path(url.rsplit("///", 1)[-1]).resolve()


def backup_dir():
    path = Path(current_app.config.get("BACKUP_DIR", "./backups")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_backup(path: Path):
    reset_engine()
    with sqlite3.connect(database_path()) as source, sqlite3.connect(path) as destination:
        source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        source.backup(destination)


@web.get("/backup")
@login_required
def backup_index():
    if not g.user.is_superuser:
        return render_template("backup/index.html", backups=[])
    items = []
    for path in sorted(backup_dir().glob("accounting_backup_*.db"), reverse=True):
        items.append({"filename": path.name, "created_at": datetime.fromtimestamp(path.stat().st_mtime),
                      "size_bytes": path.stat().st_size})
    return render_template("backup/index.html", backups=items)


@web.get("/backup/download")
@superuser_required
def backup_download():
    name = f"accounting_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    path = backup_dir() / f"temp_download_{datetime.now():%Y%m%d_%H%M%S}.db"
    create_backup(path)
    return send_file(path, as_attachment=True, download_name=name, mimetype="application/octet-stream")


@web.post("/backup/create")
@superuser_required
def backup_create():
    path = backup_dir() / f"accounting_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    create_backup(path)
    flash("Το αντίγραφο δημιουργήθηκε.", "success")
    return finish("web.backup_index")


@web.post("/backup/restore")
@superuser_required
def backup_restore_upload():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename.lower().endswith(".db"):
        flash("Επιλέξτε έγκυρο αρχείο .db.", "error")
        return finish("web.backup_index")
    pre = backup_dir() / f"pre_restore_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(database_path(), pre)
    uploaded.save(database_path())
    reset_engine()
    flash("Η βάση δεδομένων επαναφέρθηκε επιτυχώς.", "success")
    return finish("web.backup_index")


@web.post("/backup/restore/<path:filename>")
@superuser_required
def backup_restore(filename):
    source = backup_dir() / filename
    if not source.exists():
        abort(404)
    pre = backup_dir() / f"pre_restore_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(database_path(), pre)
    shutil.copy2(source, database_path())
    reset_engine()
    flash("Η βάση δεδομένων επαναφέρθηκε επιτυχώς.", "success")
    return finish("web.backup_index")


@web.post("/backup/delete/<path:filename>")
@superuser_required
def backup_delete(filename):
    path = backup_dir() / filename
    if not path.exists():
        abort(404)
    path.unlink()
    flash("Το αντίγραφο διαγράφηκε.", "success")
    return finish("web.backup_index")
