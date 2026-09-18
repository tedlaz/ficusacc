"""Per-company key/value settings."""

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class SettingModel(SQLModel, table=True):
    """One row per (company, key); values are stored as strings and parsed by app.web.settings."""

    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("company_id", "key", name="uq_settings_company_key"),)

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    key: str = Field(max_length=50)
    value: str = Field(max_length=200)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
