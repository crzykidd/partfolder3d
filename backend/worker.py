"""PartFolder 3D — arq worker entry point.

Phase 0: empty task set. Connects to Redis and idles.
Phase 3: build_zip_bundle — builds a ZIP of an item directory for download.
Phase 4: render_item — renders mesh thumbnails; scheduled-job framework;
         cleanup_expired_bundles (cron) + exec_scheduled_job (run-now).
Phase 5: process_import_session — scrape/sidecar-read/tag-reconcile for import wizard.
         inbox_scan — daily scheduled job to detect new inbox subfolders.
Phase 6: library_reconcile_scan — daily scheduled reconciliation scan;
         apply_review_item — apply an approved ReviewItem's proposed_action.
Phase 7: build_zip_bundle extended with include_print_history support;
         share_link_expiry_cleanup — daily cleanup of expired/old share links.
Phase 9: db_backup — daily in-process DB + config backup with retention pruning.
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
    "inbox_scan": (
        "Scan the inbox directory for new asset folders and enqueue import sessions.",
        "daily at 02:00 UTC",
    ),
    "library_reconcile_scan": (
        "Daily library reconciliation scan — detects out-of-band edits, new/removed files, "
        "sidecar drift, orphans, and integrity issues.",
        "daily at 03:00 UTC",
    ),
    "share_link_expiry_cleanup": (
        "Mark expired share links and prune old audit events (Phase 7).",
        "daily at 01:00 UTC",
    ),
    "db_backup": (
        "Daily in-process DB + config backup (db.json + secret.key). "
        "Library files are NOT included — back up /data/library/ separately.",
        "daily at 04:00 UTC",
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
      2. Walks the item's directory, zipping all files.
      3. If bundle.include_print_history is True:
           - If bundle.requester_user_id is set (authenticated): includes ALL
             print records (public + private) as a JSON sidecar.
           - If bundle.requester_user_id is None (public/anonymous): includes
             ONLY public print records (visibility='public').
         SECURITY: private records are NEVER included for anonymous/public bundles.
      4. Writes the ZIP to DATA_DIR/zips/<bundle_id>.zip.
      5. Updates bundle.status to "ready" (or "failed" on error).
    """
    import json  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.download_bundle import DownloadBundle  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.print_record import PrintRecord  # noqa: PLC0415

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

            # Determine print history inclusion
            include_history = bundle.include_print_history
            requester_user_id = bundle.requester_user_id
            print_records: list[PrintRecord] = []

            if include_history:
                # SECURITY: only public records for anonymous/public bundles
                pr_query = sa.select(PrintRecord).where(
                    PrintRecord.item_id == bundle.item_id
                )
                if requester_user_id is None:
                    # Public/anonymous: only public records
                    pr_query = pr_query.where(PrintRecord.visibility == "public")
                # Authenticated: all records (public + private)
                pr_result = await db.execute(
                    pr_query.order_by(PrintRecord.created_at.asc())
                )
                print_records = list(pr_result.scalars().all())

            # Build the ZIP
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in sorted(item_dir.rglob("*")):
                    if file_path.is_file():
                        arcname = file_path.relative_to(item_dir)
                        zf.write(str(file_path), str(arcname))

                # Append print history as JSON if requested
                if include_history and print_records:
                    history_data = [
                        {
                            "id": r.id,
                            "note": r.note,
                            "visibility": r.visibility,
                            "date": r.date.isoformat() if r.date else None,
                            "printer": r.printer,
                            "material": r.material,
                            "filament_color": r.filament_color,
                            "nozzle_diameter": r.nozzle_diameter,
                            "layer_height": r.layer_height,
                            "supports": r.supports,
                            "success": r.success,
                            "rating": r.rating,
                            "filament_length_mm": r.filament_length_mm,
                            "filament_weight_g": r.filament_weight_g,
                            "estimated_print_time_s": r.estimated_print_time_s,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                        }
                        for r in print_records
                    ]
                    zf.writestr(
                        "print-history.json",
                        json.dumps(history_data, indent=2),
                    )
                    log.info(
                        "build_zip_bundle: included %d print record(s) in bundle %s "
                        "(authenticated=%s)",
                        len(print_records),
                        bundle_id,
                        requester_user_id is not None,
                    )

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
# Phase 4 helpers
# ---------------------------------------------------------------------------


async def _reconcile_render_images(
    item_id: int,
    item_dir: Path,
    renders_dir: Path,
    _db: "object | None" = None,
) -> None:
    """Reconcile source=render Image rows to exactly match renders/<sha>.png files.

    Rules:
    - Create Image rows for render PNGs not yet tracked.
    - Delete Image rows whose render PNG no longer exists on disk.
    - No duplicates: match by (item_id, source=render, path).
    - Default image: if the item has NO is_default image, set one render row as
      default so the catalog thumbnail appears.  If a curated image is already
      default, leave it.
    - Render images sort after curated images (order > max curated order).
    - Excludes render Images from the sidecar (handled in items.py).
    - Best-effort: caller catches and logs any exception.

    Args:
        _db: Optional AsyncSession.  When None (production), opens and commits its
             own SessionLocal.  When provided (tests), uses that session and flushes
             without committing (caller manages the transaction).
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.image import Image, ImageSource  # noqa: PLC0415

    async def _do_reconcile(db: object) -> None:  # type: ignore[type-arg]
        """Inner function that operates on a given session."""
        renders_dir_path = renders_dir
        if not renders_dir_path.exists():
            # No renders dir → clean up stale DB rows
            stale = await db.execute(  # type: ignore[union-attr]
                sa.select(Image).where(
                    Image.item_id == item_id,
                    Image.source == ImageSource.render,
                )
            )
            for row in stale.scalars().all():
                await db.delete(row)  # type: ignore[union-attr]
            return

        # Collect current render PNGs
        current_render_paths: set[str] = set()
        for p in renders_dir_path.iterdir():
            if p.is_file() and p.suffix.lower() == ".png":
                current_render_paths.add(str(p.relative_to(item_dir)))

        # Load existing render Image rows
        existing_result = await db.execute(  # type: ignore[union-attr]
            sa.select(Image).where(
                Image.item_id == item_id,
                Image.source == ImageSource.render,
            )
        )
        existing_render_rows: list[Image] = list(existing_result.scalars().all())
        existing_by_path: dict[str, Image] = {row.path: row for row in existing_render_rows}

        # Delete stale rows (and their files)
        for path, row in list(existing_by_path.items()):
            if path not in current_render_paths:
                try:
                    stale_file = item_dir / path
                    if stale_file.exists():
                        stale_file.unlink()
                except OSError as exc:
                    log.warning(
                        "_reconcile_render_images: could not remove %s: %s", path, exc
                    )
                await db.delete(row)  # type: ignore[union-attr]
                del existing_by_path[path]

        # Compute starting order for new render rows
        curated_order_result = await db.execute(  # type: ignore[union-attr]
            sa.select(sa.func.max(Image.order)).where(
                Image.item_id == item_id,
                Image.source.in_([ImageSource.scraped, ImageSource.uploaded]),
            )
        )
        max_curated_order = curated_order_result.scalar_one_or_none() or 0

        render_order_result = await db.execute(  # type: ignore[union-attr]
            sa.select(sa.func.max(Image.order)).where(
                Image.item_id == item_id,
                Image.source == ImageSource.render,
            )
        )
        max_render_order = render_order_result.scalar_one_or_none() or 0
        next_order = max(max_curated_order, max_render_order) + 1

        # Create rows for new render PNGs
        for rp in sorted(current_render_paths):
            if rp not in existing_by_path:
                new_img = Image(
                    item_id=item_id,
                    path=rp,
                    source=ImageSource.render,
                    is_default=False,
                    order=next_order,
                )
                db.add(new_img)  # type: ignore[union-attr]
                next_order += 1

        await db.flush()  # type: ignore[union-attr]

        # Set a render as default if the item has NO is_default image
        default_result = await db.execute(  # type: ignore[union-attr]
            sa.select(Image).where(
                Image.item_id == item_id,
                Image.is_default.is_(True),
            ).limit(1)
        )
        has_default = default_result.scalar_one_or_none() is not None
        if not has_default and current_render_paths:
            first_render_result = await db.execute(  # type: ignore[union-attr]
                sa.select(Image).where(
                    Image.item_id == item_id,
                    Image.source == ImageSource.render,
                ).order_by(Image.order).limit(1)
            )
            first_render = first_render_result.scalar_one_or_none()
            if first_render is not None:
                first_render.is_default = True
                log.info(
                    "_reconcile_render_images: set render %s as default for item %s",
                    first_render.path, item_id,
                )

        log.info(
            "_reconcile_render_images: item=%s current_renders=%d",
            item_id, len(current_render_paths),
        )

    if _db is not None:
        # Test/caller-supplied session: run core logic without commit
        await _do_reconcile(_db)
    else:
        # Production: open a fresh session, commit on success
        async with SessionLocal() as db:
            await _do_reconcile(db)
            await db.commit()


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

        # Reconcile render Image rows to match current renders/*.png files.
        # This is best-effort: a DB hiccup must not crash the worker.
        try:
            await _reconcile_render_images(item_id, item_dir, renders_dir)
        except Exception:
            log.exception(
                "render_item: reconcile_render_images failed for item %s (non-fatal)", item_id
            )

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
# Phase 16 task — per-object mesh analysis
# ---------------------------------------------------------------------------


async def analyze_item(ctx: dict, item_id: int) -> None:
    """Analyze model files for an item: colors + estimated filament grams.

    Phase 16: sha-cached — skips files whose analysis already matches the
    current sha256.  Best-effort: one bad file does not fail the whole item.
    Results stored in File.object_analysis (JSONB).

    Enqueued alongside render_item on item create / file change / rescan.
    """
    import json  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.setting import Setting  # noqa: PLC0415
    from app.worker.mesh_analysis import MESH_ANALYSIS_EXTENSIONS, analyze_file  # noqa: PLC0415

    # Load settings (density + infill) once; fall back to defaults
    async with SessionLocal() as db:
        density_result = await db.execute(
            sa.select(Setting).where(Setting.key == "estimate.filament_density_g_cm3")
        )
        infill_result = await db.execute(
            sa.select(Setting).where(Setting.key == "estimate.infill_pct")
        )
        density_row = density_result.scalar_one_or_none()
        infill_row = infill_result.scalar_one_or_none()

    density_g_cm3 = 1.24
    infill_pct = 15.0
    try:
        if density_row:
            density_g_cm3 = float(json.loads(density_row.value))
    except Exception:
        pass
    try:
        if infill_row:
            infill_pct = float(json.loads(infill_row.value))
    except Exception:
        pass

    # Load item + model files
    async with SessionLocal() as db:
        item_result = await db.execute(sa.select(Item).where(Item.id == item_id))
        item = item_result.scalar_one_or_none()
        if item is None:
            log.warning("analyze_item: item %s not found", item_id)
            return

        item_dir = Path(item.dir_path)

        files_result = await db.execute(
            sa.select(File).where(
                File.item_id == item_id,
                File.role == FileRole.model,
            )
        )
        model_files = list(files_result.scalars().all())

    if not model_files:
        log.debug("analyze_item: item %s has no model files", item_id)
        return

    analyzed = 0
    skipped = 0
    errors = 0

    for f in model_files:
        file_path = item_dir / f.path
        suffix = file_path.suffix.lower()

        if suffix not in MESH_ANALYSIS_EXTENSIONS:
            skipped += 1
            continue

        if not file_path.exists():
            log.warning("analyze_item: item=%s file %s not found on disk", item_id, f.path)
            errors += 1
            continue

        # sha-cache: skip if analysis already keyed to current sha256
        current_sha = f.sha256
        existing = getattr(f, "object_analysis", None)
        if (
            isinstance(existing, dict)
            and current_sha
            and existing.get("source_hash") == current_sha
        ):
            skipped += 1
            log.debug("analyze_item: item=%s %s cached (sha match)", item_id, f.path)
            continue

        try:
            result = analyze_file(
                file_path,
                density_g_cm3=density_g_cm3,
                infill_pct=infill_pct,
                source_hash=current_sha,
            )
            async with SessionLocal() as db:
                await db.execute(
                    sa.update(File)
                    .where(File.id == f.id)
                    .values(object_analysis=result)
                )
                await db.commit()
            analyzed += 1
            log.info(
                "analyze_item: item=%s analyzed %s → %d object(s) %.1fg est.",
                item_id, f.path,
                result.get("total_objects", 0),
                result.get("total_est_grams", 0.0),
            )
        except Exception as exc:
            errors += 1
            log.warning(
                "analyze_item: item=%s file %s failed: %s",
                item_id, f.path, exc,
            )

    log.info(
        "analyze_item: item=%s done — analyzed=%d skipped=%d errors=%d",
        item_id, analyzed, skipped, errors,
    )


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


# ---------------------------------------------------------------------------
# Phase 5 tasks
# ---------------------------------------------------------------------------


async def process_import_session(ctx: dict, session_id: str) -> None:
    """Pre-fill an ImportSession: scrape URL, read sidecar, reconcile tags.

    Flow:
      1. Load the session.
      2. If source_url: scrape metadata/images/tags/creator.
      3. If inbox_folder: walk for model files; read sidecar if present.
      4. Reconcile raw tags (alias map → confirmed; unknown → pending suggestions).
      5. Set session status to 'pending_wizard' (or 'failed' on error).

    The wizard does NOT auto-finalize — the user must confirm and call /commit.
    A failure marks the session 'failed' with an error message; the wizard can
    still be used manually (manual path always works).
    """
    import asyncio  # noqa: PLC0415
    import uuid as _uuid  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionImage,
        ImportSessionStatus,
        ImportSourceType,
    )
    from app.models.site_capability import SiteCapability  # noqa: PLC0415
    from app.storage.scraper import extract_domain, scrape_url  # noqa: PLC0415

    try:
        sid = _uuid.UUID(session_id)
    except ValueError:
        log.error("process_import_session: invalid session_id %r", session_id)
        return

    # Reload session
    async with SessionLocal() as db:
        result = await db.execute(
            sa.select(ImportSession).where(ImportSession.id == sid)
        )
        session = result.scalar_one_or_none()
        if session is None:
            log.warning("process_import_session: session %s not found", session_id)
            return
        if session.status not in (
            ImportSessionStatus.processing, ImportSessionStatus.draft
        ):
            log.info(
                "process_import_session: session %s is %s, skipping",
                session_id, session.status,
            )
            return

    raw_tags: list[str] = []
    scraped_title: str | None = None
    scraped_description: str | None = None
    scraped_creator: str | None = None
    scraped_creator_url: str | None = None
    scraped_license: str | None = None
    scraped_source_site: str | None = None
    image_urls: list[str] = []
    error: str | None = None

    try:
        async with SessionLocal() as db:
            session_result = await db.execute(
                sa.select(ImportSession).where(ImportSession.id == sid)
            )
            session = session_result.scalar_one()

            # ---- URL scrape ----
            if session.source_url:
                from app.config import settings as _settings  # noqa: PLC0415

                domain = extract_domain(session.source_url)

                # Check site capability
                cap_result = await db.execute(
                    sa.select(SiteCapability).where(SiteCapability.domain == domain)
                )
                cap = cap_result.scalar_one_or_none()

                should_scrape = True
                if cap and cap.is_manual_only:
                    should_scrape = False
                    log.info(
                        "process_import_session: %s is manual-only, skip scrape",
                        domain,
                    )

                if should_scrape:
                    # Run blocking scrape in a thread
                    sr = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: scrape_url(
                            session.source_url,
                            timeout=_settings.SCRAPE_TIMEOUT,
                            max_images=_settings.SCRAPE_MAX_IMAGES,
                        ),
                    )

                    # Record/update site capability
                    if cap is None:
                        cap = SiteCapability(
                            domain=domain,
                            can_scrape_metadata=not sr.blocked,
                            can_scrape_images=bool(sr.image_urls),
                            requires_token=False,
                            is_manual_only=False,
                        )
                        db.add(cap)
                    else:
                        if not sr.blocked:
                            cap.can_scrape_metadata = True
                        if sr.image_urls:
                            cap.can_scrape_images = True
                    cap.last_probed_at = datetime.now(UTC)
                    await db.flush()

                    if not sr.blocked:
                        scraped_title = sr.title
                        scraped_description = sr.description
                        scraped_creator = sr.creator_name
                        scraped_creator_url = sr.creator_profile_url
                        scraped_license = sr.license
                        scraped_source_site = sr.source_site
                        raw_tags = sr.raw_tags
                        image_urls = sr.image_urls

            # ---- Inbox folder sidecar read ----
            if session.source_type == ImportSourceType.inbox and session.inbox_folder:
                from pathlib import Path  # noqa: PLC0415

                from app.storage.sidecar import read_sidecar  # noqa: PLC0415

                inbox_path = Path(session.inbox_folder)
                # Try to find a sidecar in the folder
                # Look for .yml files that match the sidecar pattern
                yml_files = list(inbox_path.glob("*.yml"))
                for yf in yml_files:
                    sc = read_sidecar(inbox_path, yf.stem, yf.stem)
                    if sc is None:
                        # Try the generic sidecar reader with the file directly
                        try:
                            import yaml  # noqa: PLC0415
                            raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
                            if isinstance(raw, dict) and "schema_version" in raw:
                                # It's a sidecar; extract fields
                                if not scraped_title and raw.get("title"):
                                    scraped_title = str(raw["title"])
                                if not scraped_description and raw.get("description"):
                                    scraped_description = str(raw["description"])
                                src = raw.get("source") or {}
                                if isinstance(src, dict):
                                    if not session.source_url and src.get("url"):
                                        # Update session source URL
                                        session.source_url = str(src["url"])
                                    if not scraped_license and src.get("license"):
                                        scraped_license = str(src["license"])
                                    if not scraped_source_site and src.get("site"):
                                        scraped_source_site = str(src["site"])
                                creator_d = raw.get("creator")
                                if isinstance(creator_d, dict) and not scraped_creator:
                                    scraped_creator = creator_d.get("name")
                                    scraped_creator_url = creator_d.get("profile_url")
                                sidecar_tags = [
                                    str(t) for t in (raw.get("tags") or [])
                                ]
                                if sidecar_tags:
                                    raw_tags = sidecar_tags + raw_tags
                        except Exception:
                            log.debug("process_import_session: sidecar parse failed for %s", yf)
                    else:
                        # read_sidecar succeeded
                        if not scraped_title:
                            scraped_title = sc.title
                        if not scraped_description:
                            scraped_description = sc.description
                        if not scraped_license:
                            scraped_license = sc.license
                        if not scraped_source_site:
                            scraped_source_site = sc.source_site
                        if sc.creator:
                            scraped_creator = sc.creator.name
                            scraped_creator_url = sc.creator.profile_url
                        raw_tags = list(sc.tags) + raw_tags
                    break  # Use first sidecar found

            # ---- Tag reconciliation ----
            from app.routers.import_sessions import reconcile_tags  # noqa: PLC0415

            tag_state = (
                await reconcile_tags(db, raw_tags)
                if raw_tags
                else {"confirmed": [], "pending": []}
            )

            # ---- Update session ----
            if not session.suggested_title:
                session.suggested_title = scraped_title
            if not session.confirmed_title:
                session.confirmed_title = scraped_title
            if not session.description:
                session.description = scraped_description
            if not session.license:
                session.license = scraped_license
            if not session.source_site:
                session.source_site = scraped_source_site
            if not session.creator_name:
                session.creator_name = scraped_creator
            if not session.creator_profile_url:
                session.creator_profile_url = scraped_creator_url
            if not session.creator_source_site and scraped_source_site:
                session.creator_source_site = scraped_source_site

            session.tag_state = tag_state
            session.status = ImportSessionStatus.pending_wizard
            session.updated_at = datetime.now(UTC)

            # Add scraped image URLs to session images
            existing_orders = {img.order for img in await _load_session_images(db, sid)}
            for i, img_url in enumerate(image_urls):
                order = i + len(existing_orders)
                img = ImportSessionImage(
                    session_id=session.id,
                    path=img_url,
                    is_url=True,
                    source="scrape",
                    order=order,
                    is_default=(order == 0 and not existing_orders),
                )
                db.add(img)

            await db.commit()
            log.info(
                "process_import_session: session %s → pending_wizard "
                "(tags confirmed=%d pending=%d images=%d)",
                session_id,
                len(tag_state.get("confirmed", [])),
                len(tag_state.get("pending", [])),
                len(image_urls),
            )

    except Exception as exc:
        error = str(exc)
        log.exception("process_import_session: failed for session %s", session_id)
        async with SessionLocal() as db:
            try:
                res = await db.execute(
                    sa.select(ImportSession).where(ImportSession.id == sid)
                )
                session = res.scalar_one_or_none()
                if session:
                    session.status = ImportSessionStatus.failed
                    session.error = error
                    session.updated_at = datetime.now(UTC)
                    await db.commit()
            except Exception:
                log.exception(
                    "process_import_session: could not mark session %s failed",
                    session_id,
                )


async def _load_session_images(db: object, sid: object) -> list:
    """Helper: load existing ImportSessionImage rows for a session."""
    import sqlalchemy as sa  # noqa: PLC0415

    from app.models.import_session import ImportSessionImage  # noqa: PLC0415

    result = await db.execute(  # type: ignore[union-attr]
        sa.select(ImportSessionImage).where(ImportSessionImage.session_id == sid)
    )
    return list(result.scalars().all())


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

_SCHED_FUNCS = {
    "expired_zip_cleanup": _cleanup_expired_bundles_core,
    "inbox_scan": _inbox_scan_core,
    "library_reconcile_scan": _library_reconcile_scan_core,
    "share_link_expiry_cleanup": _share_link_expiry_cleanup_core,
    "db_backup": _db_backup_core,
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


async def apply_review_item(ctx: dict, review_item_id: int) -> None:
    """Apply an approved ReviewItem's proposed_action.

    Called by POST /api/reviews/{id}/approve.  Reads the ReviewItem, applies its
    proposed_action via the reconcile engine, writes a ChangeLog entry, and marks
    the ReviewItem as approved.
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.review_item import ReviewItem  # noqa: PLC0415
    from app.worker.reconcile import apply_review_item_action  # noqa: PLC0415

    async with SessionLocal() as db:
        result = await db.execute(
            sa.select(ReviewItem).where(ReviewItem.id == review_item_id)
        )
        rv = result.scalar_one_or_none()
        if rv is None:
            log.warning("apply_review_item: review_item %s not found", review_item_id)
            return
        await apply_review_item_action(db, rv)
        await db.commit()
    log.info("apply_review_item: review_item %s applied and approved", review_item_id)


class WorkerSettings:
    """arq worker configuration."""

    functions = [
        build_zip_bundle,
        render_item,
        exec_scheduled_job,
        # Phase 5
        process_import_session,
        # Phase 6
        apply_review_item,
        # Phase 16
        analyze_item,
    ]

    cron_jobs = [
        cron(cron_expired_zip_cleanup, hour=0, minute=0, run_at_startup=False),
        cron(cron_share_link_expiry_cleanup, hour=1, minute=0, run_at_startup=False),
        cron(cron_inbox_scan, hour=2, minute=0, run_at_startup=False),
        cron(cron_library_reconcile_scan, hour=3, minute=0, run_at_startup=False),
        cron(cron_db_backup, hour=4, minute=0, run_at_startup=False),
    ]

    on_startup = startup

    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 600  # 10 minutes (render can be slow)


async def main() -> None:
    """Run the worker (used when executing this file directly)."""
    from arq.worker import create_worker

    # NOTE: arq's Worker(...) takes `functions` (a list) as its first positional
    # arg — passing the settings class directly raises "'type' object is not
    # iterable". create_worker() reads the settings-class attributes and builds
    # the Worker correctly.
    worker = create_worker(WorkerSettings)  # type: ignore[arg-type]
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(main())
