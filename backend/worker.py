"""PartFolder 3D — arq worker entry point.

Phase 0: empty task set. Connects to Redis and idles.
Phase 3: build_zip_bundle — builds a ZIP of an item directory for download.
Phase 4: render_item — renders mesh thumbnails; scheduled-job framework;
         cleanup_expired_bundles (cron) + exec_scheduled_job (run-now).
"""

import asyncio
import logging
import os
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from arq.connections import RedisSettings
from arq.cron import cron

log = logging.getLogger(__name__)


def get_redis_settings() -> RedisSettings:
    """Parse REDIS_URL into arq RedisSettings."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    return RedisSettings.from_dsn(url)


# ---------------------------------------------------------------------------
# Scheduled-job registry
# ---------------------------------------------------------------------------
# Maps a stable job name (used as ScheduledJob.name in DB) → (description, schedule_str).
# The cron expressions are listed next to each wrapper below.
SCHEDULED_JOB_REGISTRY: dict[str, tuple[str, str]] = {
    "expired_zip_cleanup": (
        "Delete ZIP bundles that have passed their expiry time (~24 h).",
        "daily at 00:00 UTC",
    ),
    "placeholder_reindex": (
        "Placeholder for future full-library reindex (no-op until Phase 6).",
        "daily at 01:00 UTC",
    ),
}


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


# ---------------------------------------------------------------------------
# Phase 3 tasks
# ---------------------------------------------------------------------------


async def build_zip_bundle(ctx: dict, bundle_id: str) -> None:
    """Build a ZIP archive of an item directory for download.

    PRD §11: queued ZIP with ~1-day expiry.  This task:
      1. Reads the DownloadBundle row.
      2. Walks the item's directory, zipping all files (model files, images,
         renders — but NOT print history, which has no PrintRecord yet in
         Phase 3).  The print-history-in-ZIP checkbox from PRD §11 is stubbed
         off (no PrintRecord model yet).
      3. Writes the ZIP to DATA_DIR/zips/<bundle_id>.zip.
      4. Updates bundle.status to "ready" (or "failed" on error).
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.download_bundle import DownloadBundle  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415

    try:
        bundle_uuid = uuid.UUID(bundle_id)
    except ValueError:
        log.error("build_zip_bundle: invalid bundle_id %r", bundle_id)
        return

    async with SessionLocal() as db:
        try:
            # Load the bundle
            result = await db.execute(
                sa.select(DownloadBundle).where(DownloadBundle.id == bundle_uuid)
            )
            bundle = result.scalar_one_or_none()
            if bundle is None:
                log.warning("build_zip_bundle: bundle %s not found", bundle_id)
                return

            # Load the item
            item_result = await db.execute(
                sa.select(Item).where(Item.id == bundle.item_id)
            )
            item = item_result.scalar_one_or_none()
            if item is None:
                bundle.status = "failed"
                bundle.error_message = f"Item {bundle.item_id} not found"
                await db.commit()
                return

            item_dir = Path(item.dir_path)
            if not item_dir.exists():
                bundle.status = "failed"
                bundle.error_message = f"Item directory not found: {item_dir}"
                await db.commit()
                return

            # Ensure zips output directory exists
            zips_dir = Path(settings.DATA_DIR) / "zips"
            zips_dir.mkdir(parents=True, exist_ok=True)
            zip_path = zips_dir / f"{bundle_id}.zip"

            # Build the ZIP
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in sorted(item_dir.rglob("*")):
                    if file_path.is_file():
                        arcname = file_path.relative_to(item_dir)
                        zf.write(str(file_path), str(arcname))

            bundle.status = "ready"
            bundle.bundle_path = str(zip_path)
            await db.commit()
            log.info("build_zip_bundle: bundle %s ready at %s", bundle_id, zip_path)

        except Exception as exc:
            log.exception("build_zip_bundle: error building bundle %s", bundle_id)
            # Try to mark the bundle as failed
            try:
                result = await db.execute(
                    sa.select(DownloadBundle).where(DownloadBundle.id == bundle_uuid)
                )
                bundle = result.scalar_one_or_none()
                if bundle:
                    bundle.status = "failed"
                    bundle.error_message = str(exc)
                    # Remove partial zip if it exists
                    zip_path = Path(settings.DATA_DIR) / "zips" / f"{bundle_id}.zip"
                    if zip_path.exists():
                        zip_path.unlink()
                    await db.commit()
            except Exception:
                log.exception(
                    "build_zip_bundle: could not mark bundle %s as failed", bundle_id
                )


# ---------------------------------------------------------------------------
# Phase 4 tasks
# ---------------------------------------------------------------------------


async def render_item(ctx: dict, item_id: int) -> None:
    """Render all mesh files for an item into renders/<sha256>.png.

    PRD §7: SHA-256-keyed cache — skips files whose render already exists.
    Re-renders if the file hash changed (new sha256 → different cache key).

    A render failure marks the Job row failed and is visible in the monitor.
    It does NOT crash the worker and does NOT block item creation or rescan.

    Non-mesh files (Blender/CAD/gcode) are silently skipped with no Job failure.
    """
    import hashlib  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.worker.job_tracker import (  # noqa: PLC0415
        create_job,
        finish_job,
        update_job_progress,
    )
    from app.worker.render_mesh import (  # noqa: PLC0415
        MESH_EXTENSIONS,
        RenderError,
        render_mesh_file,
    )

    # Create the Job row
    async with SessionLocal() as db:
        job_id = await create_job(
            db, "render", payload={"item_id": item_id}, item_id=item_id
        )
        await db.commit()

    try:
        # Load item + model files
        async with SessionLocal() as db:
            item_result = await db.execute(
                sa.select(Item).where(Item.id == item_id)
            )
            item = item_result.scalar_one_or_none()
            if item is None:
                async with SessionLocal() as db2:
                    await finish_job(
                        db2, job_id, succeeded=False,
                        error=f"Item {item_id} not found"
                    )
                    await db2.commit()
                return

            item_dir = Path(item.dir_path)
            renders_dir = item_dir / "renders"

            files_result = await db.execute(
                sa.select(File).where(
                    File.item_id == item_id,
                    File.role == FileRole.model,
                )
            )
            model_files = list(files_result.scalars().all())

        if not model_files:
            async with SessionLocal() as db:
                await finish_job(
                    db, job_id, succeeded=True,
                    log_text="No model files to render."
                )
                await db.commit()
            return

        resolution = settings.RENDER_RESOLUTION
        rendered: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for idx, f in enumerate(model_files):
            file_path = item_dir / f.path
            suffix = file_path.suffix.lower()

            # Skip non-mesh types gracefully
            if suffix not in MESH_EXTENSIONS:
                skipped.append(f.path)
                continue

            if not file_path.exists():
                errors.append(f"{f.path}: file not found on disk")
                continue

            # Compute sha256 (use cached value or hash now)
            sha = f.sha256
            if not sha:
                h = hashlib.sha256()
                with file_path.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        h.update(chunk)
                sha = h.hexdigest()

            render_path = renders_dir / f"{sha}.png"
            if render_path.exists():
                skipped.append(f"{f.path} (cached)")
                continue

            try:
                renders_dir.mkdir(parents=True, exist_ok=True)
                png_bytes = render_mesh_file(file_path, resolution=resolution)
                render_path.write_bytes(png_bytes)
                rendered.append(f.path)
                log.info(
                    "render_item: item=%s rendered %s → renders/%s.png",
                    item_id, f.path, sha[:12],
                )
            except RenderError as exc:
                errors.append(f"{f.path}: {exc}")
                log.warning("render_item: item=%s %s", item_id, exc)
            except Exception as exc:
                errors.append(f"{f.path}: unexpected error: {exc}")
                log.exception("render_item: item=%s unexpected error for %s", item_id, f.path)

            # Update progress after each file
            pct = int((idx + 1) / len(model_files) * 90)
            async with SessionLocal() as db:
                await update_job_progress(db, job_id, pct)
                await db.commit()

        # Final job status
        log_lines = []
        if rendered:
            log_lines.append(f"Rendered: {', '.join(rendered)}")
        if skipped:
            log_lines.append(f"Skipped: {', '.join(skipped)}")
        if errors:
            log_lines.append(f"Errors: {'; '.join(errors)}")

        succeeded = not (errors and not rendered)
        async with SessionLocal() as db:
            await finish_job(
                db, job_id,
                succeeded=succeeded,
                error=("; ".join(errors) if not succeeded else None),
                log_text="\n".join(log_lines) or "No mesh files to render.",
            )
            await db.commit()

    except Exception as exc:
        log.exception("render_item: unexpected top-level error for item %s", item_id)
        async with SessionLocal() as db:
            await finish_job(db, job_id, succeeded=False, error=str(exc))
            await db.commit()


# ---------------------------------------------------------------------------
# Concrete scheduled-job functions
# ---------------------------------------------------------------------------


async def _cleanup_expired_bundles_core(ctx: dict) -> None:
    """Delete expired DownloadBundle rows and their ZIP files.

    PRD §11: bundles expire after ~1 day.  This runs as a cron job so even
    bundles not re-requested by the user are eventually cleaned up.
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.download_bundle import DownloadBundle  # noqa: PLC0415

    cutoff = datetime.now(UTC)
    deleted = 0

    async with SessionLocal() as db:
        result = await db.execute(
            sa.select(DownloadBundle).where(DownloadBundle.expires_at <= cutoff)
        )
        expired = result.scalars().all()

        for bundle in expired:
            if bundle.bundle_path:
                p = Path(bundle.bundle_path)
                if p.exists():
                    try:
                        p.unlink()
                    except OSError as exc:
                        log.warning(
                            "cleanup_expired_bundles: could not delete %s: %s", p, exc
                        )
            await db.delete(bundle)
            deleted += 1

        await db.commit()

    log.info("cleanup_expired_bundles: deleted %d expired bundle(s)", deleted)


async def _placeholder_reindex_core(_ctx: dict) -> None:
    """Placeholder for the full library reindex (Phase 6).  Currently a no-op."""
    log.info("placeholder_reindex: no-op (Phase 6 not yet implemented)")


# ---------------------------------------------------------------------------
# exec_scheduled_job — dispatches named job; used for "run-now" from the API
# ---------------------------------------------------------------------------

_SCHED_FUNCS = {
    "expired_zip_cleanup": _cleanup_expired_bundles_core,
    "placeholder_reindex": _placeholder_reindex_core,
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
        # Determine next_run hour based on job
        hour = 0 if name == "expired_zip_cleanup" else 1
        await _sj_finish(name, error=error, hour=hour, minute=0)


# ---------------------------------------------------------------------------
# arq cron wrappers (one per scheduled job — arq cron can't pass args)
# ---------------------------------------------------------------------------


async def cron_expired_zip_cleanup(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "expired_zip_cleanup")


async def cron_placeholder_reindex(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "placeholder_reindex")


# ---------------------------------------------------------------------------
# Worker startup hook — seed ScheduledJob table
# ---------------------------------------------------------------------------


async def startup(ctx: dict) -> None:
    """Ensure all registered scheduled jobs have a row in scheduled_jobs."""
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.scheduled_job import ScheduledJob  # noqa: PLC0415

    async with SessionLocal() as db:
        for name, (description, schedule) in SCHEDULED_JOB_REGISTRY.items():
            result = await db.execute(
                sa.select(ScheduledJob).where(ScheduledJob.name == name)
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                sj = ScheduledJob(
                    name=name,
                    description=description,
                    schedule=schedule,
                )
                db.add(sj)
        await db.commit()
    log.info("startup: scheduled_jobs table seeded")


# ---------------------------------------------------------------------------
# Worker settings
# ---------------------------------------------------------------------------


class WorkerSettings:
    """arq worker configuration."""

    functions = [
        build_zip_bundle,
        render_item,
        exec_scheduled_job,
    ]

    cron_jobs = [
        cron(cron_expired_zip_cleanup, hour=0, minute=0, run_at_startup=False),
        cron(cron_placeholder_reindex, hour=1, minute=0, run_at_startup=False),
    ]

    on_startup = startup

    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 600  # 10 minutes (render can be slow)


async def main() -> None:
    """Run the worker (used when executing this file directly)."""
    from arq import Worker

    worker = Worker(WorkerSettings)  # type: ignore[arg-type]
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(main())
