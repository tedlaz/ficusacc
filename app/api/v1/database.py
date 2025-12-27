"""Database backup and restore API routes."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.dependencies import CurrentUser
from app.infrastructure.database.session import reset_database_connections

router = APIRouter()


def get_db_path() -> Path:
    """Extract the database file path from the DATABASE_URL."""
    # DATABASE_URL format: sqlite+aiosqlite:///./accounting.db
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        # Extract path after ///
        path_str = url.split("///")[-1]
        return Path(path_str).resolve()
    raise ValueError("Only SQLite databases support backup/restore")


def get_backup_dir() -> Path:
    """Get the backup directory, creating it if necessary."""
    backup_dir = Path("./backups")
    backup_dir.mkdir(exist_ok=True)
    return backup_dir


class BackupInfo(BaseModel):
    """Information about a backup file."""

    filename: str
    created_at: str
    size_bytes: int


class BackupListResponse(BaseModel):
    """Response containing list of available backups."""

    backups: list[BackupInfo]


class BackupResponse(BaseModel):
    """Response after creating a backup."""

    message: str
    filename: str


class RestoreResponse(BaseModel):
    """Response after restoring from backup."""

    message: str


@router.get("/backup", response_class=FileResponse)
async def download_backup(
    current_user: CurrentUser,
) -> FileResponse:
    """
    Download a backup of the current database.

    Only superusers can perform this operation.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can backup the database",
        )

    db_path = get_db_path()
    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database file not found",
        )

    # Create a timestamped backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"accounting_backup_{timestamp}.db"

    return FileResponse(
        path=str(db_path),
        filename=backup_filename,
        media_type="application/octet-stream",
    )


@router.post("/backup", response_model=BackupResponse)
async def create_backup(
    current_user: CurrentUser,
) -> BackupResponse:
    """
    Create a server-side backup of the database.

    Only superusers can perform this operation.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can backup the database",
        )

    db_path = get_db_path()
    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database file not found",
        )

    backup_dir = get_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"accounting_backup_{timestamp}.db"
    backup_path = backup_dir / backup_filename

    try:
        shutil.copy2(db_path, backup_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {str(e)}",
        )

    return BackupResponse(
        message="Backup created successfully",
        filename=backup_filename,
    )


@router.get("/backups", response_model=BackupListResponse)
async def list_backups(
    current_user: CurrentUser,
) -> BackupListResponse:
    """
    List all available server-side backups.

    Only superusers can view backups.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can view backups",
        )

    backup_dir = get_backup_dir()
    backups: list[BackupInfo] = []

    for file in sorted(backup_dir.glob("accounting_backup_*.db"), reverse=True):
        stat = file.stat()
        # Parse timestamp from filename
        try:
            timestamp_str = file.stem.replace("accounting_backup_", "")
            created_dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            created_at = created_dt.isoformat()
        except ValueError:
            created_at = datetime.fromtimestamp(stat.st_mtime).isoformat()

        backups.append(
            BackupInfo(
                filename=file.name,
                created_at=created_at,
                size_bytes=stat.st_size,
            )
        )

    return BackupListResponse(backups=backups)


@router.post("/restore", response_model=RestoreResponse)
async def restore_from_upload(
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(description="SQLite database file to restore")],
) -> RestoreResponse:
    """
    Restore the database from an uploaded backup file.

    Only superusers can perform this operation.
    WARNING: This will replace the current database!
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can restore the database",
        )

    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Please upload a .db file",
        )

    db_path = get_db_path()

    # Create a backup of current database before restore
    backup_dir = get_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore_backup = backup_dir / f"pre_restore_backup_{timestamp}.db"

    try:
        if db_path.exists():
            shutil.copy2(db_path, pre_restore_backup)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create pre-restore backup: {str(e)}",
        )

    try:
        # Write uploaded file to database path
        content = await file.read()
        with open(db_path, "wb") as f:
            f.write(content)
    except Exception as e:
        # Try to restore from pre-restore backup
        if pre_restore_backup.exists():
            shutil.copy2(pre_restore_backup, db_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore database: {str(e)}",
        )

    # Reset database connections to use the new database file
    await reset_database_connections()

    return RestoreResponse(
        message="Η βάση δεδομένων επαναφέρθηκε επιτυχώς.",
    )


@router.post("/restore/{backup_filename}", response_model=RestoreResponse)
async def restore_from_server_backup(
    backup_filename: str,
    current_user: CurrentUser,
) -> RestoreResponse:
    """
    Restore the database from a server-side backup.

    Only superusers can perform this operation.
    WARNING: This will replace the current database!
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can restore the database",
        )

    backup_dir = get_backup_dir()
    backup_path = backup_dir / backup_filename

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup file not found",
        )

    db_path = get_db_path()

    # Create a backup of current database before restore
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore_backup = backup_dir / f"pre_restore_backup_{timestamp}.db"

    try:
        if db_path.exists():
            shutil.copy2(db_path, pre_restore_backup)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create pre-restore backup: {str(e)}",
        )

    try:
        shutil.copy2(backup_path, db_path)
    except Exception as e:
        # Try to restore from pre-restore backup
        if pre_restore_backup.exists():
            shutil.copy2(pre_restore_backup, db_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore database: {str(e)}",
        )

    # Reset database connections to use the new database file
    await reset_database_connections()

    return RestoreResponse(
        message="Η βάση δεδομένων επαναφέρθηκε επιτυχώς.",
    )


@router.delete("/backups/{backup_filename}")
async def delete_backup(
    backup_filename: str,
    current_user: CurrentUser,
) -> dict[str, str]:
    """
    Delete a server-side backup file.

    Only superusers can delete backups.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can delete backups",
        )

    backup_dir = get_backup_dir()
    backup_path = backup_dir / backup_filename

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup file not found",
        )

    try:
        backup_path.unlink()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete backup: {str(e)}",
        )

    return {"message": "Backup deleted successfully"}
