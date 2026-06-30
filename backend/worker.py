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


# ---------------------------------------------------------------------------
# Task imports (from app.worker.tasks.*)
# ---------------------------------------------------------------------------
from app.worker.tasks.analysis import analyze_item  # noqa: E402
from app.worker.tasks.bundles import build_zip_bundle  # noqa: E402
from app.worker.tasks.import_session import (  # noqa: E402, F401
    _try_agentql_fallback,
    process_import_session,
)
from app.worker.tasks.render import _reconcile_render_images, render_item  # noqa: E402, F401
from app.worker.tasks.reviews import apply_review_item  # noqa: E402
from app.worker.tasks.scheduled import (  # noqa: E402
    cron_db_backup,
    cron_expired_zip_cleanup,
    cron_inbox_scan,
    cron_library_reconcile_scan,
    cron_share_link_expiry_cleanup,
    exec_scheduled_job,
)

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
