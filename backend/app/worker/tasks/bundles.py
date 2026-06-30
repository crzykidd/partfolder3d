"""Bundle tasks — ZIP download bundles and cleanup."""
from __future__ import annotations

import logging
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)


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
