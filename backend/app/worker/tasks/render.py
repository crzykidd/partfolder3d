"""Render task — render mesh thumbnails."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


async def _reconcile_render_images(
    item_id: int,
    item_dir: Path,
    renders_dir: Path,
    _db: object | None = None,
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


async def render_item(ctx: dict, item_id: int, retry_of_job_id: str | None = None) -> None:
    """Render all mesh files for an item into renders/<sha256>.png.

    PRD §7: SHA-256-keyed cache — skips files whose render already exists.
    Re-renders if the file hash changed (new sha256 → different cache key).

    A render failure marks the Job row failed and is visible in the monitor.
    It does NOT crash the worker and does NOT block item creation or rescan.

    Non-mesh files (Blender/CAD/gcode) are silently skipped with no Job failure.

    Error handling:
    - Per-file RenderError / RenderTimeout → appended to errors[], job marked
      failed at the end but the function RETURNS NORMALLY so arq does not retry
      (which would create duplicate Job rows).
    - Unexpected Exception (DB hiccup, I/O error) → job marked failed, function
      returns normally (same reasoning: no retry, no duplicate rows).
    - BaseException (asyncio.CancelledError from arq timeout / shutdown) →
      job marked failed best-effort using a fresh DB session, then re-raised so
      arq knows the task was cancelled.
    """
    import hashlib  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.image import Image  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.worker.job_tracker import (  # noqa: PLC0415
        create_job,
        finish_job,
        update_job_progress,
    )
    from app.worker.render_mesh import MESH_EXTENSIONS, RenderError  # noqa: PLC0415
    from app.worker.render_subprocess import RenderTimeout, run_render_subprocess  # noqa: PLC0415

    # ---- Background-render mode gate (before creating a Job row) ----
    render_mode = settings.RENDER_MODE
    if render_mode == "off":
        log.info("render_item: RENDER_MODE=off — skipping render for item %s", item_id)
        return
    if render_mode == "no_images":
        async with SessionLocal() as db:
            img_count = await db.scalar(
                sa.select(sa.func.count())
                .select_from(Image)
                .where(Image.item_id == item_id)
            )
        if img_count:
            log.info(
                "render_item: RENDER_MODE=no_images and item %s already has %d image(s)"
                " — skipping render",
                item_id,
                img_count,
            )
            return

    # Create the Job row — capture arq's internal job_id for cancel/abort support
    async with SessionLocal() as db:
        job_id = await create_job(
            db,
            "render",
            payload={"item_id": item_id},
            item_id=item_id,
            arq_job_id=ctx.get("job_id"),
            retry_of_job_id=retry_of_job_id,
        )
        await db.commit()

    _job_finalized = False

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
                _job_finalized = True
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
            _job_finalized = True
            return

        resolution = settings.RENDER_RESOLUTION
        timeout_s = settings.RENDER_TIMEOUT_S
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
                png_bytes = await run_render_subprocess(
                    file_path, resolution=resolution, timeout_s=timeout_s
                )
                render_path.write_bytes(png_bytes)
                rendered.append(f.path)
                log.info(
                    "render_item: item=%s rendered %s → renders/%s.png",
                    item_id, f.path, sha[:12],
                )
            except (RenderError, RenderTimeout) as exc:
                errors.append(f"{f.path}: {exc}")
                log.warning("render_item: item=%s %s", item_id, exc)

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
        _job_finalized = True

    except Exception as exc:
        # Unexpected pipeline error (DB hiccup, I/O, etc.).
        # Mark failed and return normally — arq must not retry (that would spawn
        # a duplicate Job row since we already created one above).
        if not _job_finalized:
            log.exception("render_item: unexpected error for item %s", item_id)
            try:
                async with SessionLocal() as db:
                    await finish_job(db, job_id, succeeded=False, error=str(exc))
                    await db.commit()
            except Exception:
                log.exception(
                    "render_item: failed to finalize job %s on unexpected error", job_id
                )

    except BaseException:
        # asyncio.CancelledError (arq job_timeout / graceful shutdown).
        # Best-effort finalization using a FRESH session (the in-flight one may
        # be poisoned), then re-raise so arq knows the task was interrupted.
        if not _job_finalized:
            log.error(
                "render_item: cancelled/shutdown for item %s — finalizing job %s as failed",
                item_id,
                job_id,
            )
            try:
                async with SessionLocal() as db:
                    await finish_job(
                        db, job_id,
                        succeeded=False,
                        error="worker stopped / cancelled",
                    )
                    await db.commit()
            except Exception:
                log.exception(
                    "render_item: failed to finalize job %s on cancellation", job_id
                )
        raise
