"""Baseline the existing HomeAccounting schema.

Revision ID: 20260809_01
Revises:
Create Date: 2026-08-09
"""

from alembic import op
from sqlmodel import SQLModel

from app.infrastructure.database import models  # noqa: F401

revision = "20260809_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_all is intentionally idempotent so this revision can baseline existing SQLite files.
    SQLModel.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(bind=op.get_bind())
