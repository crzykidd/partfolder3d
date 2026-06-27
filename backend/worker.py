"""PartFolder 3D — arq worker entry point.

Phase 0: empty task set. Connects to Redis and idles.
Phase 3: build_zip_bundle — builds a ZIP of an item directory for download.
Background jobs (scan, render, import) are added in Phase 4+.
"""

import asyncio
import logging
import os
import uuid
import zipfile
from pathlib import Path

from arq.connections import RedisSettings

log = logging.getLogger(__name__)


def get_redis_settings() -> RedisSettings:
    """Parse REDIS_URL into arq RedisSettings."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    # arq RedisSettings.from_dsn parses redis:// URLs
    return RedisSettings.from_dsn(url)


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
# Worker settings
# ---------------------------------------------------------------------------


class WorkerSettings:
    """arq worker configuration."""

    functions = [build_zip_bundle]
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 300  # 5 minutes default timeout


async def main() -> None:
    """Run the worker (used when executing this file directly)."""
    from arq import Worker

    worker = Worker(WorkerSettings)  # type: ignore[arg-type]
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(main())
