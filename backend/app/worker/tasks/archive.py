"""Archive extraction task — auto-extract ZIP files for an item.

Phase B (render-rework-B): uploaded/imported ZIPs are expanded into the item
directory so their contents become first-class files (browsable, downloadable,
thumbnailed, and analyzed like any other file).

Behaviour
---------
- For each role=zip file in the item: extract using the safe extractor in
  app.storage.archive (zip-slip rejection, junk filtering, size/count caps).
- On success: discard the original .zip (the whole-item ZIP is reconstructable
  via build_zip_bundle — keeping the original would just waste disk space).
- A bad archive records an error but never fails the entire task; other ZIPs
  in the same item are still processed.
- After extraction: re-inventory the item dir and synchronise File rows, then
  enqueue analyze_item + render_item so extracted STL/OBJ/3MF files flow
  through the normal metadata/thumbnail pipeline.

Issue #18: a Job row is now created at task start so extraction is visible
in the Jobs monitor.  The row is marked succeeded/failed when the task ends.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


async def extract_archives(ctx: dict, item_id: int) -> None:
    """Worker task: extract all ZIP files for the given item.

    Args:
        ctx:     arq worker context dict (contains job_id for Job row linking).
        item_id: DB id of the item to process.
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.services.item_helpers import _enqueue_analyze, _enqueue_render  # noqa: PLC0415
    from app.storage.archive import ArchiveError, extract_zip  # noqa: PLC0415
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    # ------------------------------------------------------------------ #
    # Create Job row so extraction is visible in the Jobs monitor          #
    # ------------------------------------------------------------------ #
    job_id = None
    try:
        async with SessionLocal() as db:
            job_id = await create_job(
                db,
                "extract_archives",
                payload={"item_id": item_id},
                item_id=item_id,
                arq_job_id=ctx.get("job_id"),
            )
            await db.commit()
    except Exception:
        log.exception(
            "extract_archives: failed to create Job row for item %s — continuing without tracking",
            item_id,
        )

    async def _finish(
        succeeded: bool,
        error: str | None = None,
        log_text: str | None = None,
    ) -> None:
        if job_id is None:
            return
        try:
            async with SessionLocal() as db:
                await finish_job(db, job_id, succeeded=succeeded, error=error, log_text=log_text)
                await db.commit()
        except Exception:
            log.exception("extract_archives: failed to finalize Job row %s", job_id)

    # ------------------------------------------------------------------ #
    # 1. Load item + zip files                                             #
    # ------------------------------------------------------------------ #
    async with SessionLocal() as db:
        item_result = await db.execute(sa.select(Item).where(Item.id == item_id))
        item = item_result.scalar_one_or_none()
        if item is None:
            log.warning("extract_archives: item %s not found — skipping", item_id)
            await _finish(succeeded=False, error=f"Item {item_id} not found")
            return

        item_dir = Path(item.dir_path)

        all_files_result = await db.execute(
            sa.select(File).where(File.item_id == item_id)
        )
        all_file_rows = list(all_files_result.scalars().all())

    zip_file_rows = [f for f in all_file_rows if f.role == FileRole.zip]
    if not zip_file_rows:
        log.debug("extract_archives: item %s has no zip files — nothing to do", item_id)
        await _finish(succeeded=True, log_text="No zip files found.")
        return

    # Existing relative paths for collision detection (includes zip files themselves)
    existing_paths: set[str] = {f.path for f in all_file_rows}
    extracted_any = False

    # ------------------------------------------------------------------ #
    # 2. Extract each ZIP (best-effort)                                   #
    # ------------------------------------------------------------------ #
    for zip_row in zip_file_rows:
        zip_path = item_dir / zip_row.path

        if not zip_path.exists():
            log.warning(
                "extract_archives: item=%s zip missing on disk: %s",
                item_id, zip_row.path,
            )
            continue

        # Exclude the zip itself from the collision set for this extraction
        paths_without_self = existing_paths - {zip_row.path}

        try:
            result = extract_zip(
                zip_path,
                item_dir,
                existing_paths=paths_without_self,
            )
        except ArchiveError as exc:
            log.error(
                "extract_archives: item=%s zip=%s failed (ArchiveError): %s",
                item_id, zip_row.path, exc,
            )
            # Leave the original .zip in place so the user can inspect it
            continue
        except Exception:
            log.exception(
                "extract_archives: item=%s zip=%s unexpected error",
                item_id, zip_row.path,
            )
            continue

        # On success: delete the original .zip from disk
        try:
            zip_path.unlink()
        except OSError as exc:
            log.warning(
                "extract_archives: item=%s could not delete %s: %s",
                item_id, zip_row.path, exc,
            )

        log.info(
            "extract_archives: item=%s zip=%s done — "
            "extracted=%d skipped=%d errors=%d",
            item_id,
            zip_row.path,
            len(result.extracted),
            len(result.skipped),
            len(result.errors),
        )

        # Update known paths so subsequent ZIPs in the same item do not collide
        existing_paths.update(result.extracted)
        existing_paths.discard(zip_row.path)
        extracted_any = True

    if not extracted_any:
        log.info(
            "extract_archives: item=%s — no ZIPs extracted successfully", item_id
        )
        await _finish(succeeded=False, error="No ZIPs extracted successfully")
        return

    # ------------------------------------------------------------------ #
    # 3. Rescan inventory: synchronise File rows with current on-disk state
    # ------------------------------------------------------------------ #
    from app.storage.inventory import inventory_item  # noqa: PLC0415
    from app.storage.paths import sidecar_name  # noqa: PLC0415

    async with SessionLocal() as db:
        # Reload item in this session (dir_path / title / key needed)
        item_result = await db.execute(sa.select(Item).where(Item.id == item_id))
        item = item_result.scalar_one_or_none()
        if item is None:
            log.warning(
                "extract_archives: item %s disappeared before rescan", item_id
            )
            await _finish(succeeded=False, error="Item disappeared before rescan")
            return

        item_dir = Path(item.dir_path)
        sc_name = sidecar_name(item.title, item.key)

        # Current File rows keyed by relative path
        files_result = await db.execute(
            sa.select(File).where(File.item_id == item_id)
        )
        current_rows: dict[str, File] = {
            f.path: f for f in files_result.scalars().all()
        }

        # Walk the item dir to find the current on-disk state
        records = inventory_item(item_dir, sc_name)
        on_disk: dict[str, object] = {r.relative_path: r for r in records}

        # Remove rows for files no longer on disk (the extracted .zip files)
        removed = 0
        for path, row in list(current_rows.items()):
            if path not in on_disk:
                await db.delete(row)
                removed += 1

        # Add rows for newly extracted files
        added = 0
        for rec in records:
            if rec.relative_path not in current_rows:
                new_f = File(
                    item_id=item.id,
                    path=rec.relative_path,
                    role=rec.role,
                    size=rec.size,
                    sha256=rec.sha256,
                    mtime=rec.mtime,
                    last_seen_size=rec.size,
                    last_seen_mtime=rec.mtime,
                )
                db.add(new_f)
                added += 1

        await db.commit()
        log.info(
            "extract_archives: item=%s inventory resync done — added=%d removed=%d",
            item_id, added, removed,
        )

    # ------------------------------------------------------------------ #
    # 4. Enqueue analyze + render for the extracted files                 #
    # ------------------------------------------------------------------ #
    # The item is already committed here, so a fresh session can safely hold the
    # queued Job rows written by the enqueue helpers (visible before the workers
    # start — #20/#30).
    async with SessionLocal() as db:
        await _enqueue_analyze(item_id, pool=ctx.get("redis"), db=db)
        await _enqueue_render(item_id, pool=ctx.get("redis"), db=db)
        await db.commit()
    log.info(
        "extract_archives: item=%s enqueued analyze + render", item_id
    )

    await _finish(
        succeeded=True,
        log_text=f"Extraction complete — added={added} removed={removed}",
    )
