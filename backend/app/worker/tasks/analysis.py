"""Analysis task — per-object mesh analysis."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


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
