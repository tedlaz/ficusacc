"""Company settings: the catalogue of known keys and typed get/set over the settings table."""

from dataclasses import dataclass

from sqlmodel import Session, select

from app.infrastructure.database.models import SettingModel


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    help: str
    default: bool


SETTINGS: dict[str, Setting] = {
    "allow_inactive_accounts": Setting(
        key="allow_inactive_accounts",
        label="Εγγραφές σε ανενεργούς λογαριασμούς",
        help="Επιτρέπει την επιλογή ανενεργών λογαριασμών στις φόρμες εγγραφών, "
        "για διόρθωση παλαιών κινήσεων. Κανονικά μένει κλειστό.",
        default=False,
    ),
}


def _to_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def company_settings(db: Session, company_id: int) -> dict[str, bool]:
    """Every known key with its stored value or default."""
    stored = {
        row.key: row.value
        for row in db.exec(select(SettingModel).where(SettingModel.company_id == company_id)).all()
    }
    return {key: _to_bool(stored.get(key), setting.default) for key, setting in SETTINGS.items()}


def get_setting(db: Session, company_id: int, key: str) -> bool:
    return company_settings(db, company_id)[key]


def set_setting(db: Session, company_id: int, key: str, value: bool) -> None:
    if key not in SETTINGS:
        raise KeyError(key)
    row = db.exec(
        select(SettingModel).where(SettingModel.company_id == company_id, SettingModel.key == key)
    ).first()
    if row is None:
        row = SettingModel(company_id=company_id, key=key, value="")
        db.add(row)
    row.value = "1" if value else "0"
