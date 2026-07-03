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
Phase B: extract_archives — auto-extract uploaded/imported ZIPs into the item dir.
"""

import asyncio
import logging
import os

from arq.connections import RedisSettings
from arq.cron import cron

log = logging.getLogger(__name__)


def get_redis_settings() -> RedisSettings:
    """Parse the configured REDIS_URL into arq RedisSettings.

    Uses ``settings.REDIS_URL`` (same source and password-bearing default as the
    API) rather than a bare ``os.environ`` fallback, so a bare-metal worker run
    never silently drops the Redis password / requirepass.
    """
    from app.config import settings  # noqa: PLC0415

    return RedisSettings.from_dsn(settings.REDIS_URL)


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
    "job_history_retention": (
        "Daily hard-delete of old job rows past their retention window "
        "(JOB_RETENTION_SUCCEEDED_DAYS / JOB_RETENTION_FAILED_DAYS).",
        "daily at 04:00 UTC",
    ),
    "orphan_cleanup": (
        "Daily reclamation: purge soft-deleted items under DATA_DIR/trash older "
        "than TRASH_RETENTION_DAYS, and report (or delete, per ORPHAN_PRINTS_DELETE) "
        "orphaned files under items' prints/ dirs.",
        "daily at 05:00 UTC",
    ),
}


# ---------------------------------------------------------------------------
# Task imports (from app.worker.tasks.*)
# ---------------------------------------------------------------------------
from app.config import settings  # noqa: E402
from app.worker.arq_pool import job_deserializer, job_serializer  # noqa: E402
from app.worker.tasks.analysis import analyze_item  # noqa: E402
from app.worker.tasks.archive import extract_archives  # noqa: E402
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
    cron_job_history_retention,
    cron_library_reconcile_scan,
    cron_orphan_cleanup,
    cron_share_link_expiry_cleanup,
    exec_scheduled_job,
)

# ---------------------------------------------------------------------------
# Worker startup hook — seed ScheduledJob table + crash recovery
# ---------------------------------------------------------------------------


# Idempotent job types — safe to re-run.  Each maps Job.type → the arq task name;
# all three tasks take a single positional ``item_id`` and their Job payload
# carries ``{"item_id": ...}``, so a crashed run can be re-enqueued verbatim.  A
# completed render/analyze just cache-hits (SHA-256), and extract_archives is a
# no-op once the archive is already unpacked.  Any Job.type NOT listed here is
# treated as NON-idempotent (side-effecting) and is only marked failed, never
# re-run — e.g. backup, import_session commit, zip_bundle.
_IDEMPOTENT_JOB_TASKS: dict[str, str] = {
    "render": "render_item",
    "analyze": "analyze_item",
    "extract_archives": "extract_archives",
}


async def _recover_orphaned_jobs(
    ctx: dict,
    _db: object | None = None,
) -> None:
    """Reap ALL jobs left 'running' by a crashed/restarted worker.

    At startup the worker has nothing in flight, so every Job row still in
    'running' status was abandoned by a previous worker.  We mark each one
    'failed' (with a clear error + finished_at) so it stops appearing as running
    forever and becomes eligible for the retention cron.  For IDEMPOTENT job
    types (see ``_IDEMPOTENT_JOB_TASKS`` — render / analyze / extract_archives,
    all safe to re-run) we additionally re-enqueue the task, deduped by
    (task, item_id).  NON-idempotent types are marked failed ONLY and NOT re-run,
    so a half-finished side-effecting job is surfaced rather than silently
    repeated.

    'queued' rows are intentionally NOT touched: no code path writes them today
    (issue #20), and once one does, a queued row may still be a live entry in the
    Redis queue that will run normally after the restart.

    Args:
        ctx:  arq worker context dict (must contain 'redis' key when there are
              idempotent orphans to re-enqueue).
        _db:  Optional AsyncSession for testing (mirrors the _reconcile_render_images
              pattern).  When None (production), opens its own SessionLocal.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.job import Job  # noqa: PLC0415

    async def _do_recover(db: object) -> dict[str, list[int]]:  # type: ignore[type-arg]
        """Inner: mark orphans failed; return {task_name: [item_id, ...]} to enqueue."""
        result = await db.execute(  # type: ignore[union-attr]
            sa.select(Job).where(Job.status == "running")
        )
        orphans: list[Job] = list(result.scalars().all())

        if not orphans:
            return {}

        idempotent_n = sum(1 for j in orphans if j.type in _IDEMPOTENT_JOB_TASKS)
        log.warning(
            "startup: %d orphaned 'running' job(s) found "
            "(%d idempotent → fail + re-queue, %d non-idempotent → fail only) — reaping",
            len(orphans),
            idempotent_n,
            len(orphans) - idempotent_n,
        )

        now = datetime.now(UTC)
        to_enqueue: dict[str, list[int]] = {}
        seen: dict[str, set[int]] = {}

        for job in orphans:
            job.status = "failed"  # type: ignore[union-attr]
            job.finished_at = now  # type: ignore[union-attr]
            task_name = _IDEMPOTENT_JOB_TASKS.get(job.type)  # type: ignore[union-attr]
            if task_name is not None:
                job.error = "orphaned by worker restart — re-queued"  # type: ignore[union-attr]
                item_id: int | None = (job.payload or {}).get("item_id")  # type: ignore[union-attr]
                if item_id is not None:
                    bucket = seen.setdefault(task_name, set())
                    if item_id not in bucket:
                        bucket.add(item_id)
                        to_enqueue.setdefault(task_name, []).append(int(item_id))
            else:
                job.error = (  # type: ignore[union-attr]
                    "orphaned by worker restart — not auto-retried "
                    "(non-idempotent job type; re-run manually if needed)"
                )

        await db.flush()  # type: ignore[union-attr]
        return to_enqueue

    if _db is not None:
        to_enqueue = await _do_recover(_db)
    else:
        async with SessionLocal() as db:
            to_enqueue = await _do_recover(db)
            await db.commit()

    if not to_enqueue:
        return

    redis = ctx.get("redis")
    if redis is None:
        log.error("startup: no redis in ctx — cannot re-enqueue orphaned idempotent jobs")
        return

    for task_name, item_ids in to_enqueue.items():
        for item_id in item_ids:
            await redis.enqueue_job(task_name, item_id)
            log.info("startup: re-enqueued %s for item_id=%d", task_name, item_id)


async def startup(ctx: dict) -> None:
    """Seed the ScheduledJob table, apply thread caps, and recover orphaned jobs."""
    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.scheduled_job import ScheduledJob  # noqa: PLC0415

    # --- Thread caps ---
    # Set numeric-thread env vars BEFORE any render subprocess is spawned so
    # children inherit them.  The compose environment (and Dockerfile ENV) already
    # set these; this is a belt-and-suspenders defensive reset that drives them
    # all from the single RENDER_CPU_THREADS setting.
    thread_count = str(settings.RENDER_CPU_THREADS)
    for _var in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "LP_NUM_THREADS",
    ):
        os.environ[_var] = thread_count
    log.info("startup: render thread caps set to %s", thread_count)

    # --- Seed scheduled jobs ---
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

    # --- Crash recovery ---
    await _recover_orphaned_jobs(ctx)
    log.info("startup: crash recovery complete")


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
        # Phase B (render-rework-B)
        extract_archives,
    ]

    cron_jobs = [
        cron(cron_expired_zip_cleanup, hour=0, minute=0, run_at_startup=False),
        cron(cron_share_link_expiry_cleanup, hour=1, minute=0, run_at_startup=False),
        cron(cron_inbox_scan, hour=2, minute=0, run_at_startup=False),
        cron(cron_library_reconcile_scan, hour=3, minute=0, run_at_startup=False),
        cron(cron_db_backup, hour=4, minute=0, run_at_startup=False),
        cron(cron_job_history_retention, hour=4, minute=30, run_at_startup=False),
        cron(cron_orphan_cleanup, hour=5, minute=0, run_at_startup=False),
    ]

    allow_abort_jobs = True

    on_startup = startup

    redis_settings = get_redis_settings()
    # JSON job bodies instead of arq's pickle default (latent worker RCE via a
    # Redis-write primitive).  MUST match the enqueue side (app.worker.arq_pool)
    # or jobs won't deserialize.
    job_serializer = staticmethod(job_serializer)
    job_deserializer = staticmethod(job_deserializer)
    max_jobs = settings.WORKER_MAX_JOBS
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
