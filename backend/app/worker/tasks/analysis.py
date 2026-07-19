"""Analysis task — per-object mesh analysis + 3MF embedded thumbnail extraction."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


async def _reconcile_embedded_thumbnail(
    item_id: int,
    item_dir: Path,
    thumb_bytes: bytes,
    _db: object | None = None,
) -> str | None:
    """Write the embedded thumbnail to disk and create/reconcile its Image row.

    Directory layout: <item_dir>/thumbs/embedded/<sha256>.png
    SHA-cached: if the file already exists on disk (same content) we skip the
    write.  An Image row is created if one does not already exist for this path.

    Priority: embedded images are inserted AFTER scraped/uploaded images in
    order but BEFORE render images.

    Returns the item-relative thumbnail path (e.g. "thumbs/embedded/<sha>.png")
    on success, or None if the thumbnail could not be written to disk.

    Args:
        _db: Optional AsyncSession for tests; when None opens its own session.
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.image import Image, ImageSource  # noqa: PLC0415

    # Determine storage path
    sha = hashlib.sha256(thumb_bytes).hexdigest()
    thumb_dir = item_dir / "thumbs" / "embedded"
    thumb_path = thumb_dir / f"{sha}.png"
    rel_path = str(thumb_path.relative_to(item_dir))

    # Write to disk (skip if already present with same content)
    if not thumb_path.exists():
        try:
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path.write_bytes(thumb_bytes)
        except OSError as exc:
            log.warning(
                "_reconcile_embedded_thumbnail: could not write %s: %s", thumb_path, exc
            )
            return None

    async def _do_reconcile(db: object) -> None:  # type: ignore[type-arg]
        # Check if this exact path already has an Image row
        existing_result = await db.execute(  # type: ignore[union-attr]
            sa.select(Image).where(
                Image.item_id == item_id,
                Image.path == rel_path,
                Image.source == ImageSource.embedded,
            )
        )
        if existing_result.scalar_one_or_none() is not None:
            log.debug(
                "_reconcile_embedded_thumbnail: Image row already exists for %s", rel_path
            )
            return

        # Order: after curated images (scraped/uploaded), before renders
        curated_max_result = await db.execute(  # type: ignore[union-attr]
            sa.select(sa.func.max(Image.order)).where(
                Image.item_id == item_id,
                Image.source.in_([ImageSource.scraped, ImageSource.uploaded]),
            )
        )
        max_curated = curated_max_result.scalar_one_or_none() or 0

        embedded_max_result = await db.execute(  # type: ignore[union-attr]
            sa.select(sa.func.max(Image.order)).where(
                Image.item_id == item_id,
                Image.source == ImageSource.embedded,
            )
        )
        max_embedded = embedded_max_result.scalar_one_or_none() or 0

        next_order = max(max_curated, max_embedded) + 1

        new_img = Image(
            item_id=item_id,
            path=rel_path,
            source=ImageSource.embedded,
            is_default=False,
            order=next_order,
        )
        db.add(new_img)  # type: ignore[union-attr]
        await db.flush()  # type: ignore[union-attr]

        # Set as default if no higher-priority image is currently default
        default_result = await db.execute(  # type: ignore[union-attr]
            sa.select(Image).where(
                Image.item_id == item_id,
                Image.is_default.is_(True),
            ).limit(1)
        )
        has_default = default_result.scalar_one_or_none() is not None
        if not has_default:
            new_img.is_default = True
            log.info(
                "_reconcile_embedded_thumbnail: set embedded %s as default for item %s",
                rel_path, item_id,
            )

        log.info(
            "_reconcile_embedded_thumbnail: created Image row for item=%s path=%s",
            item_id, rel_path,
        )

    if _db is not None:
        await _do_reconcile(_db)
    else:
        async with SessionLocal() as db:
            await _do_reconcile(db)
            await db.commit()

    return rel_path


def _build_cap_skip_stub(source_hash: str | None, max_triangles: int) -> dict[str, Any]:
    """Build a low-confidence stub FileAnalysis for an over-cap mesh (issue #37 fix #4).

    Stored sha-keyed exactly like a normal result, so the sha-cache in
    ``_analyze_item_body`` treats it as "analyzed" and never retries the file —
    an oversized mesh gets a stable, visible "too large to analyze" state
    instead of an infinite retry loop or a silent gap in the UI.
    """
    return {
        "analyzed_at": datetime.now(UTC).isoformat(),
        "source_hash": source_hash,
        "objects": [],
        "total_objects": 0,
        "total_colors": 0,
        "total_est_grams": 0.0,
        "low_confidence": True,
        "analysis_skipped": "too_large",
        "note": f"mesh exceeds {max_triangles:,}-triangle analyze cap",
    }


def _build_sliced_analysis(
    info: dict[str, Any],
    source_hash: str | None,
) -> dict[str, Any]:
    """Build a FileAnalysis dict from 3MF slicer metadata.

    For sliced 3MF files, slicer data (filament g/m, print time) is more
    accurate than a volume estimate, so we use it as the primary analysis.
    est_method='sliced' signals to the UI that numbers are from the slicer.
    """
    # Build per-filament "objects" for display — each filament slot is one entry
    objects: list[dict[str, Any]] = []
    for fil in info.get("filament", []):
        slot = fil.get("slot", 0)
        objects.append(
            {
                "name": f"Filament {slot} ({fil.get('type') or 'unknown'})",
                "color_count": 1,
                "colors": [fil["color_hex"]] if fil.get("color_hex") else [],
                "volume_cm3": None,
                "est_grams": fil.get("used_g"),
                "est_method": "sliced",
                "watertight": None,
                "low_confidence": False,
                "dims_mm": None,
            }
        )

    # Totals
    total_g = info.get("total_filament_g")
    total_grams = round(float(total_g), 3) if total_g is not None else 0.0

    filament_list = info.get("filament", [])
    total_colors = len({
        f["color_hex"] for f in filament_list if f.get("color_hex")
    }) or len(filament_list)

    objects_total = info.get("objects_total") or len(objects) or 0

    return {
        "analyzed_at": datetime.now(UTC).isoformat(),
        "source_hash": source_hash,
        "objects": objects,
        "total_objects": objects_total,
        "total_colors": total_colors,
        "total_est_grams": total_grams,
        # Sliced-specific fields
        "est_method": "sliced",
        "sliced": True,
        "slicer": info.get("slicer"),
        "printer_model": info.get("printer_model"),
        "print_time_s": info.get("print_time_s"),
        "plate_count": info.get("plate_count", 0),
        "filament": filament_list,
        "plates": info.get("plates", []),
    }


# Cap concurrent mesh analyses (loads meshes into RAM via trimesh).  Lazy so the
# settings import stays deferred and the semaphore binds to the worker loop.
_analyze_sem: asyncio.Semaphore | None = None


def _get_analyze_sem() -> asyncio.Semaphore:
    global _analyze_sem
    if _analyze_sem is None:
        from app.config import settings  # noqa: PLC0415

        _analyze_sem = asyncio.Semaphore(max(1, settings.ANALYZE_CONCURRENCY))
    return _analyze_sem


async def analyze_item(ctx: dict, item_id: int) -> None:
    """Arq entrypoint — throttle concurrent analyses (ANALYZE_CONCURRENCY), then analyze."""
    async with _get_analyze_sem():
        await _analyze_item_inner(ctx, item_id)


async def _analyze_item_inner(ctx: dict, item_id: int) -> None:
    """Analyze model files for an item: colors + estimated filament grams.

    For 3MF files: extracts embedded thumbnail AND uses slicer metadata when
    sliced (est_method='sliced'); falls back to trimesh volume estimate when
    unsliced.

    Phase 16: sha-cached — skips files whose analysis already matches the
    current sha256.  Best-effort: one bad file does not fail the whole item.
    Results stored in File.object_analysis (JSONB).

    Enqueued alongside render_item on item create / file change / rescan.
    """
    from app.db import SessionLocal  # noqa: PLC0415
    from app.worker.job_tracker import (  # noqa: PLC0415
        claim_or_create_job,
        finish_job,
        mark_superseded,
    )

    # Issue #30: claim the queued Job row written at enqueue time (→ running), or
    # insert a fresh running row when none exists, so mesh-analysis work is
    # visible in the Jobs monitor.  Failure to track must never block analysis.
    job_id = None
    try:
        async with SessionLocal() as db:
            job_id = await claim_or_create_job(
                db,
                "analyze",
                payload={"item_id": item_id},
                item_id=item_id,
                arq_job_id=ctx.get("job_id"),
            )
            await db.commit()
    except Exception:
        log.exception(
            "analyze_item: failed to claim/create Job row for item %s"
            " — continuing without tracking",
            item_id,
        )

    # Issue #37 fix #3 (PRIMARY guard): dedup concurrent analyze jobs per item.
    # A worker restart's orphan-requeue, an enqueue-time race, or a manual
    # re-trigger can produce a second analyze Job for the same item while one is
    # already running. If so, this job is redundant — supersede it and return
    # BEFORE the expensive _analyze_item_body runs. Best-effort: a tight race
    # where two claims land in the same instant may both see zero running peers
    # (acceptable — fix #1's retry cap bounds any residual waste, and the
    # sha-cache means a second pass mostly no-ops). Only 'running' peers count
    # (not 'queued') and the current job_id is excluded, so a job can never
    # supersede itself.
    if job_id is not None:
        try:
            import sqlalchemy as sa  # noqa: PLC0415

            from app.models.job import Job  # noqa: PLC0415

            async with SessionLocal() as db:
                other_running = await db.execute(
                    sa.select(Job.id).where(
                        Job.type == "analyze",
                        Job.item_id == item_id,
                        Job.status == "running",
                        Job.id != job_id,
                    )
                )
                if other_running.scalars().first() is not None:
                    await mark_superseded(
                        db,
                        job_id,
                        reason=(
                            "deduped: another analyze job for this item is"
                            " already running"
                        ),
                    )
                    await db.commit()
                    log.info(
                        "analyze_item: item=%s deduped — concurrent analyze"
                        " already running, superseding",
                        item_id,
                    )
                    return
        except Exception:
            log.exception(
                "analyze_item: dedup check failed for item %s"
                " — continuing without dedup",
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
                await finish_job(
                    db, job_id, succeeded=succeeded, error=error, log_text=log_text
                )
                await db.commit()
        except Exception:
            log.exception("analyze_item: failed to finalize Job row %s", job_id)

    try:
        await _analyze_item_body(ctx, item_id, _finish)
    except Exception as exc:
        log.exception("analyze_item: unexpected error for item %s", item_id)
        await _finish(succeeded=False, error=str(exc))
    except BaseException:
        log.error(
            "analyze_item: cancelled/shutdown for item %s — finalizing job as failed",
            item_id,
        )
        await _finish(succeeded=False, error="worker stopped / cancelled")
        raise


async def _analyze_item_body(ctx: dict, item_id: int, _finish: Any) -> None:
    """Core analysis body; the caller finalizes the tracked Job row via *_finish*.

    *_finish* is an ``async (succeeded, error=None, log_text=None)`` callback that
    marks the claimed Job row terminal.  Every exit path here calls it so the row
    never sits in 'running' after the task ends.
    """
    import json  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.setting import Setting  # noqa: PLC0415
    from app.worker.analyze_subprocess import (  # noqa: PLC0415
        AnalyzeCapSkip,
        run_analyze_subprocess,
    )
    from app.worker.mesh_analysis import MESH_ANALYSIS_EXTENSIONS  # noqa: PLC0415
    from app.worker.threemf import read_3mf  # noqa: PLC0415

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
            await _finish(succeeded=False, error=f"Item {item_id} not found")
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
        await _finish(succeeded=True, log_text="No model files to analyze.")
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
            log.debug("analyze_item: item=%s %s cached (sha match)", item_id, f.path)
            # Still try to reconcile embedded thumbnail even if analysis is cached.
            # Also backfill thumbnail_path into the cached result when it is missing
            # (e.g. files analysed before this feature was added).
            if suffix == ".3mf":
                try:
                    info = read_3mf(file_path)
                    if info["thumbnail_bytes"]:
                        thumb_path = await _reconcile_embedded_thumbnail(
                            item_id, item_dir, info["thumbnail_bytes"]
                        )
                        if thumb_path is not None and not existing.get("thumbnail_path"):
                            updated = {**existing, "thumbnail_path": thumb_path}
                            async with SessionLocal() as db:
                                await db.execute(
                                    sa.update(File)
                                    .where(File.id == f.id)
                                    .values(object_analysis=updated)
                                )
                                await db.commit()
                except Exception as exc:
                    log.warning(
                        "analyze_item: embedded thumb reconcile failed for %s: %s",
                        f.path, exc,
                    )
            skipped += 1
            continue

        try:
            if suffix == ".3mf":
                # 3MF: read slicer metadata + extract embedded thumbnail
                info = read_3mf(file_path)

                # Always attempt to reconcile the embedded thumbnail (best-effort).
                # Capture the returned path so it can be stored per-file.
                thumb_path: str | None = None
                if info["thumbnail_bytes"]:
                    try:
                        thumb_path = await _reconcile_embedded_thumbnail(
                            item_id, item_dir, info["thumbnail_bytes"]
                        )
                    except Exception as exc:
                        log.warning(
                            "analyze_item: embedded thumb reconcile failed for %s: %s",
                            f.path, exc,
                        )

                if info["sliced"]:
                    # Use slicer data (accurate) instead of volume estimate
                    result = _build_sliced_analysis(info, current_sha)
                else:
                    # Unsliced 3MF — fall back to trimesh volume estimate, run in
                    # an isolated subprocess (issue #37 fix #2 / #4).
                    result = await run_analyze_subprocess(
                        file_path,
                        density_g_cm3=density_g_cm3,
                        infill_pct=infill_pct,
                        source_hash=current_sha,
                        timeout_s=settings.ANALYZE_TIMEOUT_S,
                        mem_limit_mb=settings.ANALYZE_MEM_LIMIT_MB,
                        max_triangles=settings.ANALYZE_MAX_TRIANGLES,
                    )

                # Store per-file thumbnail path (None when no embedded thumbnail).
                # Generic field: STL/OBJ renders can populate it in the future.
                result["thumbnail_path"] = thumb_path
            else:
                # STL / OBJ / PLY: always trimesh-based — run in an isolated
                # subprocess (issue #37 fix #2 / #4).
                result = await run_analyze_subprocess(
                    file_path,
                    density_g_cm3=density_g_cm3,
                    infill_pct=infill_pct,
                    source_hash=current_sha,
                    timeout_s=settings.ANALYZE_TIMEOUT_S,
                    mem_limit_mb=settings.ANALYZE_MEM_LIMIT_MB,
                    max_triangles=settings.ANALYZE_MAX_TRIANGLES,
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
                "analyze_item: item=%s analyzed %s → method=%s objects=%d grams=%.1f",
                item_id, f.path,
                result.get("est_method", "volume"),
                result.get("total_objects", 0),
                result.get("total_est_grams") or 0.0,
            )
        except AnalyzeCapSkip as exc:
            # Mesh too large to analyze (issue #37 fix #4) — NOT an error: store a
            # low-confidence stub, sha-keyed so it is cached and never retried.
            stub = _build_cap_skip_stub(current_sha, settings.ANALYZE_MAX_TRIANGLES)
            async with SessionLocal() as db:
                await db.execute(
                    sa.update(File)
                    .where(File.id == f.id)
                    .values(object_analysis=stub)
                )
                await db.commit()
            skipped += 1
            log.info(
                "analyze_item: item=%s file %s skipped — %s",
                item_id, f.path, exc,
            )
        except Exception as exc:
            # Covers AnalyzeTimeout / AnalyzeError (subprocess timed out or
            # crashed/OOM'd — issue #37 fix #2) as well as any other failure.
            # The worker survives; this one file is marked errored and retried
            # on the next rescan (the sha-cache does not store a result for it).
            errors += 1
            log.warning(
                "analyze_item: item=%s file %s failed: %s",
                item_id, f.path, exc,
            )

    log.info(
        "analyze_item: item=%s done — analyzed=%d skipped=%d errors=%d",
        item_id, analyzed, skipped, errors,
    )

    # An item whose files ALL failed is a failure; otherwise (some analysed, or
    # only unsupported/cached skips) the job succeeded.
    succeeded = not (errors and analyzed == 0)
    await _finish(
        succeeded=succeeded,
        error=(f"{errors} file(s) failed analysis" if not succeeded else None),
        log_text=f"analyzed={analyzed} skipped={skipped} errors={errors}",
    )
