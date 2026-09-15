"""Synchronous database integration for the Flask application."""

import unicodedata

from flask import current_app, g
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine


def fold_text(value):
    """Comparison key for Greek text: no accents, no case, no punctuation ("Ενοίκιο-Ιαν." -> "ενοικιο ιαν").

    Used for sorting and searching so "ΔΕΗ", "δεη" and "Δέη" all match and sort together.
    """
    if not isinstance(value, str):
        return value
    stripped = "".join(
        char for char in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(char)
    )
    return " ".join("".join(char if char.isalnum() else " " for char in stripped).split())


def _register_sqlite_functions(dbapi_connection, _record) -> None:
    """SQLite folds only ASCII in LIKE/lower(); expose the Unicode-aware key for Greek text."""
    dbapi_connection.create_function("fold_text", 1, fold_text, deterministic=True)


def init_engine(app) -> None:
    url = app.config["DATABASE_URL"]
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _register_sqlite_functions)
    app.extensions["sqlmodel_engine"] = engine
    SQLModel.metadata.create_all(engine)


def get_db() -> Session:
    if "db" not in g:
        g.db = Session(current_app.extensions["sqlmodel_engine"])
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def reset_engine() -> None:
    """Dispose connections after replacing the SQLite database file."""
    current_app.extensions["sqlmodel_engine"].dispose()
