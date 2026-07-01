"""Scheduled job tasks — cron wrappers, state management, exec dispatcher."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .backup import _db_backup_core
from .bundles import _cleanup_expired_bundles_core

log = logging.getLogger(__name__)


def _next_utc_midnight(hour: int = 0, minute: int = 0) -> datetime:
    """Return the next occurrence of HH:MM UTC after now."""
    now = datetime.now(UTC)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


# ---------------------------------------------------------------------------
# Scheduled-job state helpers
# ---------------------------------------------------------------------------


async def _sj_start(name: str) -> None:
    """Mark a scheduled job as running in the DB."""
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.scheduled_job import ScheduledJob  # noqa: PLC0415

    async with SessionLocal() as db:
        result = await db.execute(
            sa.select(ScheduledJob).where(ScheduledJob.name == name)
        )
        sj = result.scalar_one_or_none()
        if sj:
            sj.is_running = True
            sj.last_run_at = datetime.now(UTC)
            sj.last_run_status = None
            sj.last_run_error = None
            await db.commit()


async def _sj_finish(name: str, *, error: str | None, hour: int = 0, minute: int = 0) -> None:
    """Mark a scheduled job as done in the DB."""
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.scheduled_job import ScheduledJob  # noqa: PLC0415

    async with SessionLocal() as db:
        result = await db.execute(
            sa.select(ScheduledJob).where(ScheduledJob.name == name)
        )
        sj = result.scalar_one_or_none()
        if sj:
            sj.is_running = False
            sj.last_run_status = "failed" if error else "succeeded"
            sj.last_run_error = error
            sj.next_run_at = _next_utc_midnight(hour=hour, minute=minute)
            await db.commit()


async def _share_link_expiry_cleanup_core(ctx: dict) -> None:
    """Phase 7: Mark expired share links (no DB delete — keep for audit).

    The share_audit_events rows are retained for audit purposes.
    This job adds an 'expired' event to any link that newly crossed its
    expires_at threshold (idempotent: skips if already has an 'expired' event).
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.share_audit_event import ShareAuditEvent  # noqa: PLC0415
    from app.models.share_link import ShareLink  # noqa: PLC0415

    cutoff = datetime.now(UTC)
    marked = 0

    async with SessionLocal() as db:
        # Find links that are expired but not yet revoked and not already having
        # an 'expired' audit event
        expired_result = await db.execute(
            sa.select(ShareLink).where(
                ShareLink.expires_at <= cutoff,
                ShareLink.revoked.is_(False),
            )
        )
        for link in expired_result.scalars().all():
            # Check if we already recorded an 'expired' event
            existing = await db.execute(
                sa.select(ShareAuditEvent).where(
                    ShareAuditEvent.share_link_id == link.id,
                    ShareAuditEvent.event_type == "expired",
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue  # already recorded

            db.add(ShareAuditEvent(
                share_link_id=link.id,
                event_type="expired",
                ip_address=None,
                user_agent=None,
            ))
            marked += 1

        await db.commit()

    log.info(
        "share_link_expiry_cleanup: marked %d link(s) as expired (audit event)", marked
    )


async def _library_reconcile_scan_core(_ctx: dict) -> None:
    """Daily library reconciliation scan (Phase 6).

    Calls the reconcile engine for every item in every enabled library:
    sidecar⇄DB sync, re-render on file change, new/removed file detection,
    orphan / dead-link / integrity checks.
    """
    from app.worker.reconcile import reconcile_library_scan  # noqa: PLC0415

    stats = await reconcile_library_scan(url_validator=None)
    log.info("library_reconcile_scan: %s", stats)


async def _inbox_scan_core(ctx: dict) -> None:
    """Scan the inbox directory for new asset folders.

    Each direct subdirectory of INBOX_DIR is treated as one pending import.
    Safety: a folder is only ingested if its mtime is older than
    INBOX_MTIME_SETTLE_SECONDS (prevents picking up folders that are still
    being written — e.g. from a large network transfer).

    Detects model files + optional URL/link file + optional sidecar.
    Creates an ImportSession per new folder and enqueues process_import_session.

    Already-tracked folders (those that already have a session with the same
    inbox_folder path) are skipped.
    """
    import time  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings as _settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionFile,
        ImportSessionStatus,
        ImportSourceType,
    )
    from app.storage.inventory import MODEL_EXTENSIONS  # noqa: PLC0415

    inbox_dir = Path(_settings.INBOX_DIR)
    if not inbox_dir.is_dir():
        log.info("inbox_scan: inbox dir %s does not exist, skipping", inbox_dir)
        return

    settle = _settings.INBOX_MTIME_SETTLE_SECONDS
    now_ts = time.time()

    enqueued = 0
    skipped_settle = 0
    skipped_tracked = 0

    async with SessionLocal() as db:
        # Load all known inbox_folder paths to skip already-tracked ones
        tracked_result = await db.execute(
            sa.select(ImportSession.inbox_folder).where(
                ImportSession.inbox_folder.is_not(None),
                ImportSession.status.not_in([
                    ImportSessionStatus.cancelled,
                    ImportSessionStatus.failed,
                ]),
            )
        )
        tracked_folders: set[str] = {row[0] for row in tracked_result.all() if row[0]}

        for entry in sorted(inbox_dir.iterdir()):
            if not entry.is_dir():
                continue

            folder_str = str(entry)

            # Skip already-tracked
            if folder_str in tracked_folders:
                skipped_tracked += 1
                continue

            # mtime settle check
            try:
                stat = entry.stat()
                age_seconds = now_ts - stat.st_mtime
                if age_seconds < settle:
                    skipped_settle += 1
                    log.debug(
                        "inbox_scan: skipping %s (mtime too recent: %.1fs < %ds)",
                        entry.name, age_seconds, settle,
                    )
                    continue
            except OSError:
                continue

            # Look for model files and optional URL/link file
            model_files: list[Path] = []
            url_from_link: str | None = None

            for child in entry.rglob("*"):
                if child.is_file():
                    ext = child.suffix.lower()
                    if ext in MODEL_EXTENSIONS:
                        model_files.append(child)
                    elif ext in (".url", ".webloc", ".desktop") or child.name.lower() in (
                        "url.txt", "source.txt", "link.txt"
                    ):
                        # Try to extract a URL from the file
                        try:
                            content = child.read_text(encoding="utf-8", errors="ignore")
                            for line in content.splitlines():
                                line = line.strip()
                                if line.startswith("http"):
                                    url_from_link = line
                                    break
                                # .url file format: URL=https://...
                                if "=" in line:
                                    k, _, v = line.partition("=")
                                    if k.strip().upper() == "URL" and v.strip().startswith("http"):
                                        url_from_link = v.strip()
                                        break
                        except Exception:
                            pass

            if not model_files and not url_from_link:
                log.debug("inbox_scan: %s has no model files or URL, skipping", entry.name)
                continue

            # Find the first admin user to assign ownership
            # (inbox scan is a system operation; use admin user)
            from app.models.user import User, UserRole  # noqa: PLC0415

            admin_result = await db.execute(
                sa.select(User).where(User.role == UserRole.admin).limit(1)
            )
            admin = admin_result.scalar_one_or_none()
            if admin is None:
                log.warning("inbox_scan: no admin user found; cannot create sessions")
                break

            # Create an ImportSession for this inbox folder
            session = ImportSession(
                status=ImportSessionStatus.draft,
                source_type=ImportSourceType.inbox,
                source_url=url_from_link,
                inbox_folder=folder_str,
                suggested_title=entry.name,
                confirmed_title=entry.name,
                created_by_id=admin.id,
            )
            db.add(session)
            await db.flush()
            await db.refresh(session)

            # Record model files as session files
            for mf in model_files:
                sf = ImportSessionFile(
                    session_id=session.id,
                    staged_path=str(mf),
                    original_name=mf.name,
                    role="model",
                    size=mf.stat().st_size,
                )
                db.add(sf)

            session.status = ImportSessionStatus.processing
            await db.commit()

            # Enqueue the processing job
            try:
                from arq import create_pool  # noqa: PLC0415
                from arq.connections import RedisSettings  # noqa: PLC0415

                redis = await create_pool(
                    RedisSettings.from_dsn(_settings.REDIS_URL)
                )
                await redis.enqueue_job("process_import_session", str(session.id))
                await redis.aclose()
                enqueued += 1
            except Exception:
                log.exception(
                    "inbox_scan: failed to enqueue process job for session %s",
                    session.id,
                )

    log.info(
        "inbox_scan: found %d new import(s) (skipped settle=%d, tracked=%d)",
        enqueued, skipped_settle, skipped_tracked,
    )


# ---------------------------------------------------------------------------
# exec_scheduled_job — dispatches named job; used for "run-now" from the API
# ---------------------------------------------------------------------------

async def _job_history_retention_core(_ctx: dict) -> None:
    """Hard-delete old job rows that have aged past their retention window.

    Succeeded jobs: deleted after JOB_RETENTION_SUCCEEDED_DAYS.
    Failed / cancelled / superseded: deleted after JOB_RETENTION_FAILED_DAYS.
    Running / queued rows are never touched.
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings as _settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.job import Job  # noqa: PLC0415

    now = datetime.now(UTC)
    succeeded_cutoff = now - timedelta(days=_settings.JOB_RETENTION_SUCCEEDED_DAYS)
    failed_cutoff = now - timedelta(days=_settings.JOB_RETENTION_FAILED_DAYS)

    async with SessionLocal() as db:
        result = await db.execute(
            sa.delete(Job).where(
                sa.or_(
                    sa.and_(
                        Job.status == "succeeded",
                        Job.finished_at < succeeded_cutoff,
                    ),
                    sa.and_(
                        Job.status.in_(["failed", "cancelled", "superseded"]),
                        Job.finished_at < failed_cutoff,
                    ),
                )
            )
        )
        deleted = result.rowcount
        await db.commit()

    log.info("job_history_retention: deleted %d old job row(s)", deleted)


_SCHED_FUNCS = {
    "expired_zip_cleanup": _cleanup_expired_bundles_core,
    "inbox_scan": _inbox_scan_core,
    "library_reconcile_scan": _library_reconcile_scan_core,
    "share_link_expiry_cleanup": _share_link_expiry_cleanup_core,
    "db_backup": _db_backup_core,
    "job_history_retention": _job_history_retention_core,
}


async def exec_scheduled_job(ctx: dict, name: str) -> None:
    """Run a named scheduled job and update its ScheduledJob state row.

    Used both by the cron wrappers and by the POST /api/scheduled-jobs/{name}/run
    'run-now' endpoint (which enqueues this function by name).
    """
    if name not in _SCHED_FUNCS:
        log.error("exec_scheduled_job: unknown job name %r", name)
        return

    await _sj_start(name)
    error: str | None = None
    try:
        await _SCHED_FUNCS[name](ctx)
    except Exception as exc:
        error = str(exc)
        log.exception("exec_scheduled_job: %r failed", name)
    finally:
        # Determine next_run hour based on job name
        _hour_map = {
            "expired_zip_cleanup": 0,
            "share_link_expiry_cleanup": 1,
            "inbox_scan": 2,
            "library_reconcile_scan": 3,
            "db_backup": 4,
            "job_history_retention": 4,
        }
        hour = _hour_map.get(name, 1)
        await _sj_finish(name, error=error, hour=hour, minute=0)


# ---------------------------------------------------------------------------
# arq cron wrappers (one per scheduled job — arq cron can't pass args)
# ---------------------------------------------------------------------------


async def cron_expired_zip_cleanup(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "expired_zip_cleanup")


async def cron_share_link_expiry_cleanup(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "share_link_expiry_cleanup")


async def cron_inbox_scan(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "inbox_scan")


async def cron_library_reconcile_scan(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "library_reconcile_scan")


async def cron_db_backup(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "db_backup")


async def cron_job_history_retention(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "job_history_retention")
