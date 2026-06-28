"""PartFolder 3D — arq worker entry point.

Phase 0: empty task set. Connects to Redis and idles.
Phase 3: build_zip_bundle — builds a ZIP of an item directory for download.
Phase 4: render_item — renders mesh thumbnails; scheduled-job framework;
         cleanup_expired_bundles (cron) + exec_scheduled_job (run-now).
Phase 5: process_import_session — scrape/sidecar-read/tag-reconcile for import wizard.
         inbox_scan — daily scheduled job to detect new inbox subfolders.
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
    "inbox_scan": (
        "Scan the inbox directory for new asset folders and enqueue import sessions.",
        "daily at 02:00 UTC",
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
    "placeholder_reindex": _placeholder_reindex_core,
    "inbox_scan": _inbox_scan_core,
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


async def cron_inbox_scan(ctx: dict) -> None:
    await exec_scheduled_job(ctx, "inbox_scan")


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
        # Phase 5
        process_import_session,
    ]

    cron_jobs = [
        cron(cron_expired_zip_cleanup, hour=0, minute=0, run_at_startup=False),
        cron(cron_placeholder_reindex, hour=1, minute=0, run_at_startup=False),
        cron(cron_inbox_scan, hour=2, minute=0, run_at_startup=False),
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
