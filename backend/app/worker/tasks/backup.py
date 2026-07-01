"""Backup task — in-process DB + config backup."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)


async def _db_backup_core(_ctx: dict) -> None:
    """Phase 9: in-process DB + config backup.

    Creates a timestamped .tar.gz under /data/backups/ containing all table
    data (as JSON, gzip-compressed) and the instance secret.key.  Library
    binary files are intentionally NOT included.

    After a successful backup, old archives beyond the retention count are pruned.
    Each run is recorded as a BackupRecord in the DB.
    """
    import json  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.backup import BackupRecord  # noqa: PLC0415
    from app.models.setting import Setting  # noqa: PLC0415
    from app.worker.backup import prune_old_backups, run_db_backup  # noqa: PLC0415

    # Create a pending record
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"backup_{ts}.tar.gz"
    archive_path_str = str(Path(settings.DATA_DIR) / "backups" / filename)

    async with SessionLocal() as db:
        record = BackupRecord(
            filename=filename,
            path=archive_path_str,
            status="pending",
        )
        db.add(record)
        await db.commit()
        record_id = record.id

    try:
        archive_path = await run_db_backup(settings.DATA_DIR)
        size = archive_path.stat().st_size

        async with SessionLocal() as db:
            result = await db.execute(
                sa.select(BackupRecord).where(BackupRecord.id == record_id)
            )
            rec = result.scalar_one_or_none()
            if rec:
                rec.status = "ready"
                rec.path = str(archive_path)
                rec.filename = archive_path.name
                rec.size_bytes = size
                await db.commit()

        log.info("db_backup: backup ready at %s (%d bytes)", archive_path, size)

        # Prune old archives
        async with SessionLocal() as db:
            retention_result = await db.execute(
                sa.select(Setting).where(Setting.key == "backup.retention_count")
            )
            row = retention_result.scalar_one_or_none()
        keep = 10
        if row:
            try:
                keep = int(json.loads(row.value))
            except Exception:
                pass
        await prune_old_backups(settings.DATA_DIR, keep=keep)

    except Exception as exc:
        log.exception("db_backup: backup failed")
        async with SessionLocal() as db:
            result = await db.execute(
                sa.select(BackupRecord).where(BackupRecord.id == record_id)
            )
            rec = result.scalar_one_or_none()
            if rec:
                rec.status = "failed"
                rec.error = str(exc)
                await db.commit()
        raise
