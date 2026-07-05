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

            # Resolve default import library for this session.
            # Order: import.default_library_id setting → sole enabled library → None.
            import json as _json  # noqa: PLC0415

            from app.models.library import Library  # noqa: PLC0415
            from app.models.setting import Setting  # noqa: PLC0415

            resolved_library_id: int | None = None

            # (a) default-library setting
            setting_res = await db.execute(
                sa.select(Setting).where(Setting.key == "import.default_library_id")
            )
            setting_row = setting_res.scalar_one_or_none()
            if setting_row is not None:
                try:
                    raw_id = _json.loads(setting_row.value)
                    if isinstance(raw_id, int):
                        lib_chk = await db.execute(
                            sa.select(Library).where(
                                Library.id == raw_id, Library.enabled.is_(True)
                            )
                        )
                        if lib_chk.scalar_one_or_none() is not None:
                            resolved_library_id = raw_id
                except Exception:
                    pass

            # (b) sole enabled library
            if resolved_library_id is None:
                all_libs_res = await db.execute(
                    sa.select(Library).where(Library.enabled.is_(True))
                )
                all_libs = all_libs_res.scalars().all()
                if len(all_libs) == 1:
                    resolved_library_id = all_libs[0].id

            # Create an ImportSession for this inbox folder
            session = ImportSession(
                status=ImportSessionStatus.draft,
                source_type=ImportSourceType.inbox,
                source_url=url_from_link,
                inbox_folder=folder_str,
                suggested_title=entry.name,
                confirmed_title=entry.name,
                library_id=resolved_library_id,
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

            # Enqueue the processing job via the worker's own arq pool (ctx),
            # which is already wired to the JSON job serializer.
            try:
                await ctx["redis"].enqueue_job(
                    "process_import_session", str(session.id)
                )
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


def _dir_size_bytes(path: Path) -> int:
    """Sum the size of every regular file under *path* (best-effort)."""
    total = 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


async def _purge_trash(now: datetime) -> tuple[int, int]:
    """Hard-delete trash entries older than TRASH_RETENTION_DAYS.

    Trash lives at DATA_DIR/trash/<ts>-<key>/ (see storage.journal.move_to_trash).
    Each entry's age is taken from its filesystem mtime.  Returns
    (entries_purged, bytes_reclaimed).  Disabled (skipped) when
    TRASH_RETENTION_DAYS <= 0.
    """
    import shutil  # noqa: PLC0415

    from app.config import settings as _settings  # noqa: PLC0415

    retention_days = _settings.TRASH_RETENTION_DAYS
    if retention_days <= 0:
        log.info(
            "orphan_cleanup: trash purge disabled (TRASH_RETENTION_DAYS=%d)", retention_days
        )
        return (0, 0)

    trash_dir = Path(_settings.DATA_DIR) / "trash"
    if not trash_dir.is_dir():
        return (0, 0)

    cutoff = now - timedelta(days=retention_days)
    purged = 0
    bytes_reclaimed = 0

    for entry in sorted(trash_dir.iterdir()):
        try:
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if mtime >= cutoff:
            continue

        age_days = (now - mtime).days
        size = _dir_size_bytes(entry)
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError:
            log.exception("orphan_cleanup: failed to purge trash entry %s", entry.name)
            continue

        purged += 1
        bytes_reclaimed += size
        log.info(
            "orphan_cleanup: purged trash entry %s (age=%dd, %d bytes)",
            entry.name,
            age_days,
            size,
        )

    log.info(
        "orphan_cleanup: trash purge complete — %d entr(ies) purged, %d bytes reclaimed",
        purged,
        bytes_reclaimed,
    )
    return (purged, bytes_reclaimed)


async def _reclaim_orphaned_prints(now: datetime) -> tuple[int, int]:
    """Find files under items' prints/ dirs with no referencing PrintRecord.

    A print file is orphaned when its path (relative to the item dir) is not
    referenced by any PrintRecord.gcode_file_path / print_photo_path for that
    item.  This happens because DELETE .../print-records/{id} intentionally
    leaves the file on disk.

    Behaviour is gated on ORPHAN_PRINTS_DELETE:
      - False (default): REPORT ONLY — log a warning with the count + a bounded
        sample of paths + total bytes.  Nothing is deleted.
      - True: delete an orphan only if it is ALSO older than TRASH_RETENTION_DAYS,
        with per-file logging.

    Returns (orphans_found, bytes) — bytes deleted when deleting, else bytes that
    would be reclaimed.
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings as _settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.print_record import PrintRecord  # noqa: PLC0415

    delete = _settings.ORPHAN_PRINTS_DELETE
    age_cutoff = now - timedelta(days=max(_settings.TRASH_RETENTION_DAYS, 0))

    # item_id -> set of referenced relative paths
    referenced: dict[int, set[str]] = {}
    item_dirs: dict[int, str] = {}

    async with SessionLocal() as db:
        items_res = await db.execute(sa.select(Item.id, Item.dir_path))
        for iid, dir_path in items_res.all():
            item_dirs[iid] = dir_path

        rec_res = await db.execute(
            sa.select(
                PrintRecord.item_id,
                PrintRecord.gcode_file_path,
                PrintRecord.print_photo_path,
            )
        )
        for item_id, gcode_path, photo_path in rec_res.all():
            refs = referenced.setdefault(item_id, set())
            if gcode_path:
                refs.add(gcode_path)
            if photo_path:
                refs.add(photo_path)

    orphans: list[tuple[Path, int]] = []  # (abs_path, size)
    for item_id, dir_path in item_dirs.items():
        prints_dir = Path(dir_path) / "prints"
        if not prints_dir.is_dir():
            continue
        refs = referenced.get(item_id, set())
        for child in prints_dir.rglob("*"):
            if not child.is_file():
                continue
            try:
                rel = str(child.relative_to(dir_path))
            except ValueError:
                continue
            if rel in refs:
                continue
            try:
                size = child.stat().st_size
            except OSError:
                size = 0
            orphans.append((child, size))

    if not orphans:
        log.info("orphan_cleanup: no orphaned print files found")
        return (0, 0)

    total_bytes = sum(s for _, s in orphans)

    if not delete:
        # REPORT ONLY — bounded sample so a big backlog can't flood the log.
        sample = [str(p) for p, _ in orphans[:50]]
        log.warning(
            "orphan_cleanup: %d orphaned print file(s) found (%d bytes) — REPORT ONLY "
            "(set ORPHAN_PRINTS_DELETE=true to reclaim). Sample: %s%s",
            len(orphans),
            total_bytes,
            sample,
            " …(truncated)" if len(orphans) > 50 else "",
        )
        return (len(orphans), total_bytes)

    # DELETE mode — only files also older than the retention window.
    deleted = 0
    deleted_bytes = 0
    for path, size in orphans:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if mtime >= age_cutoff:
            log.info(
                "orphan_cleanup: keeping orphaned print %s (younger than retention window)",
                path,
            )
            continue
        try:
            path.unlink()
        except OSError:
            log.exception("orphan_cleanup: failed to delete orphaned print %s", path)
            continue
        deleted += 1
        deleted_bytes += size
        log.info("orphan_cleanup: deleted orphaned print %s (%d bytes)", path, size)

    log.info(
        "orphan_cleanup: orphaned-prints delete complete — %d of %d deleted, %d bytes reclaimed",
        deleted,
        len(orphans),
        deleted_bytes,
    )
    return (deleted, deleted_bytes)


async def _orphan_cleanup_core(_ctx: dict) -> None:
    """Daily reclamation sweep: trash purge + orphaned-prints report/delete.

    Conservative by design — every deletion is logged, defaults are safe, and the
    orphaned-prints half only deletes when ORPHAN_PRINTS_DELETE is explicitly on.
    See config.py (TRASH_RETENTION_DAYS / ORPHAN_PRINTS_DELETE) for the knobs.
    """
    now = datetime.now(UTC)
    trash_purged, trash_bytes = await _purge_trash(now)
    print_orphans, print_bytes = await _reclaim_orphaned_prints(now)
    log.info(
        "orphan_cleanup: summary — trash purged=%d (%d bytes); "
        "orphaned prints handled=%d (%d bytes)",
        trash_purged,
        trash_bytes,
        print_orphans,
        print_bytes,
    )


_SCHED_FUNCS = {
    "expired_zip_cleanup": _cleanup_expired_bundles_core,
    "inbox_scan": _inbox_scan_core,
    "library_reconcile_scan": _library_reconcile_scan_core,
    "share_link_expiry_cleanup": _share_link_expiry_cleanup_core,
    "db_backup": _db_backup_core,
    "job_history_retention": _job_history_retention_core,
    "orphan_cleanup": _orphan_cleanup_core,
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
            "orphan_cleanup": 5,
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


async def cron_orphan_cleanup(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "orphan_cleanup")
