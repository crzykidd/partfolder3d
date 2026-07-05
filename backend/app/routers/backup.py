"""Backup management API (Phase 9 — PRD §13).

Admin-only endpoints for DB + config backups.

GET    /api/admin/backups                  → list backup records
POST   /api/admin/backups/run              → trigger a backup now (enqueues worker job)
GET    /api/admin/backups/{id}/download    → download a backup archive
DELETE /api/admin/backups/{id}             → delete a backup record + archive
GET    /api/admin/backups/settings         → get retention count
PUT    /api/admin/backups/settings         → update retention count

The scheduled backup job is registered in worker.py as "db_backup" and appears
in /api/scheduled-jobs alongside the other scheduled jobs.

IMPORTANT: Library binary files are NOT backed up — this captures DB + instance
config (secret.key) only.  The admin UI must display a prominent callout.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.backup import BackupRecord
from ..models.setting import Setting
from ..models.user import User
from ..worker.arq_pool import get_arq_pool

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/backups", tags=["admin-backups"])

_RETENTION_SETTING_KEY = "backup.retention_count"
_DEFAULT_RETENTION = 10


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BackupRecordOut(BaseModel):
    id: int
    filename: str
    size_bytes: int | None
    status: str
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BackupSettingsOut(BaseModel):
    retention_count: int


class BackupSettingsUpdate(BaseModel):
    retention_count: int


class RunBackupResponse(BaseModel):
    enqueued: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_retention(db: AsyncSession) -> int:
    result = await db.execute(
        select(Setting).where(Setting.key == _RETENTION_SETTING_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return _DEFAULT_RETENTION
    try:
        return int(json.loads(row.value))
    except Exception:
        return _DEFAULT_RETENTION


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[BackupRecordOut], summary="List backup records")
async def list_backups(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BackupRecordOut]:
    """List all backup records, newest first."""
    result = await db.execute(
        select(BackupRecord).order_by(BackupRecord.created_at.desc())
    )
    rows = result.scalars().all()
    return [BackupRecordOut.model_validate(r) for r in rows]


@router.post(
    "/run",
    response_model=RunBackupResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a backup now",
)
async def run_backup_now(
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> RunBackupResponse:
    """Enqueue an immediate backup job via the arq worker.

    The job is registered as "db_backup" in the scheduled-job framework
    and can also be triggered via POST /api/scheduled-jobs/db_backup/run.
    """
    try:
        await arq.enqueue_job("exec_scheduled_job", "db_backup")
        return RunBackupResponse(enqueued=True, message="Backup job enqueued.")
    except Exception as exc:
        log.exception("run_backup_now: failed to enqueue backup job")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue backup.",
        ) from exc


@router.get(
    "/settings",
    response_model=BackupSettingsOut,
    summary="Get backup retention settings",
)
async def get_backup_settings(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BackupSettingsOut:
    """Return current backup retention settings."""
    return BackupSettingsOut(retention_count=await _get_retention(db))


@router.put(
    "/settings",
    response_model=BackupSettingsOut,
    summary="Update backup retention count",
)
async def update_backup_settings(
    body: BackupSettingsUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BackupSettingsOut:
    """Update the number of backup archives to keep (default 10)."""
    if body.retention_count < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="retention_count must be >= 1",
        )
    result = await db.execute(
        select(Setting).where(Setting.key == _RETENTION_SETTING_KEY)
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = json.dumps(body.retention_count)
    else:
        db.add(Setting(key=_RETENTION_SETTING_KEY, value=json.dumps(body.retention_count)))
    await db.flush()
    return BackupSettingsOut(retention_count=body.retention_count)


@router.get(
    "/{backup_id}/download",
    summary="Download a backup archive",
    response_class=FileResponse,
)
async def download_backup(
    backup_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Download the .tar.gz archive for a backup record."""
    result = await db.execute(select(BackupRecord).where(BackupRecord.id == backup_id))
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found.")
    if record.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Backup is not ready (status={record.status!r}).",
        )
    from pathlib import Path  # noqa: PLC0415

    p = Path(record.path)
    if not p.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Backup archive file not found on disk.",
        )
    return FileResponse(
        path=str(p),
        filename=record.filename,
        media_type="application/gzip",
    )


@router.delete(
    "/{backup_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a backup record and its archive",
)
async def delete_backup(
    backup_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a backup record and its archive file from disk."""
    result = await db.execute(select(BackupRecord).where(BackupRecord.id == backup_id))
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found.")

    p = Path(record.path)
    if p.exists():
        try:
            p.unlink()
        except OSError as exc:
            log.warning("delete_backup: could not delete file %s: %s", p, exc)

    await db.delete(record)
    await db.flush()
