"""Session authentication and request guards."""

from functools import wraps
from hmac import compare_digest
from secrets import token_urlsafe

from flask import abort, flash, g, redirect, request, session, url_for

from app.extensions import get_db
from app.infrastructure.database.models import CompanyModel, UserModel


def load_identity() -> None:
    g.user = None
    g.company = None
    user_id = session.get("user_id")
    if user_id is not None:
        user = get_db().get(UserModel, user_id)
        if user and user.is_active:
            g.user = user
        else:
            session.clear()
    company_id = session.get("company_id")
    if company_id is not None:
        company = get_db().get(CompanyModel, company_id)
        if company and company.is_active:
            g.company = company


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("web.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def company_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.company is None:
            flash("Επιλέξτε ή δημιουργήστε πρώτα μια εταιρεία.", "warning")
            return redirect(url_for("web.dashboard"))
        return view(*args, **kwargs)

    return wrapped


def superuser_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user.is_superuser:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def csrf_token() -> str:
    token = session.get("csrf_token")
    if token is None:
        token = token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf() -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    expected = session.get("csrf_token", "")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
    if not expected or not supplied or not compare_digest(expected, supplied):
        abort(400, "Invalid CSRF token")
