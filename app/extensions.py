"""Synchronous database integration for the Flask application."""

from flask import current_app, g
from sqlmodel import SQLModel, Session, create_engine


def init_engine(app) -> None:
    url = app.config["DATABASE_URL"]
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    app.extensions["sqlmodel_engine"] = create_engine(url, connect_args=connect_args)
    SQLModel.metadata.create_all(app.extensions["sqlmodel_engine"])


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
