"""Helpers for creating and updating Job rows from arq worker tasks.

Usage inside a task:
    async with SessionLocal() as db:
        job_id = await create_job(db, "render", payload={"item_id": 42}, item_id=42)
        await db.commit()

    # ... do work ...

    async with SessionLocal() as db:
        await finish_job(db, job_id, succeeded=True)
        await db.commit()
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

log = logging.getLogger(__name__)

# Statuses that cannot be overwritten by finish_job.
# cancel sets 'cancelled' before the arq abort; the task's BaseException handler
# then calls finish_job(failed) — the terminal guard prevents clobbering.
_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "superseded"}
)


async def create_job(
    db: Any,
    job_type: str,
    payload: dict[str, Any],
    item_id: int | None = None,
    arq_job_id: str | None = None,
    retry_of_job_id: str | uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a new Job row in 'running' status and return its UUID."""
    from ..models.job import Job  # noqa: PLC0415

    retry_uuid: uuid.UUID | None = None
    if retry_of_job_id is not None:
        try:
            retry_uuid = uuid.UUID(str(retry_of_job_id))
        except ValueError:
            log.warning("create_job: invalid retry_of_job_id %r — ignored", retry_of_job_id)

    job = Job(
        type=job_type,
        status="running",
        progress=0,
        payload=payload,
        item_id=item_id,
        started_at=datetime.now(UTC),
        arq_job_id=arq_job_id,
        retry_of_job_id=retry_uuid,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job.id


async def _supersede_ancestors(
    db: Any,
    ancestor_id: uuid.UUID,
    _depth: int = 0,
) -> None:
    """Walk the retry_of_job_id chain and mark each ancestor as 'superseded'.

    Called when a retry/restart job transitions to 'succeeded' so that the
    original failed job (and any intermediate retries) disappear from the
    default job list.  Guards against cycles with a max depth of 20.
    """
    from ..models.job import Job  # noqa: PLC0415

    if _depth > 20:
        log.warning(
            "_supersede_ancestors: depth limit reached at ancestor %s — stopping", ancestor_id
        )
        return

    result = await db.execute(sa.select(Job).where(Job.id == ancestor_id))
    job = result.scalar_one_or_none()
    if job is None:
        return

    job.status = "superseded"
    if job.finished_at is None:
        job.finished_at = datetime.now(UTC)
    await db.flush()

    if job.retry_of_job_id is not None:
        await _supersede_ancestors(db, job.retry_of_job_id, _depth + 1)


async def finish_job(
    db: Any,
    job_id: uuid.UUID,
    *,
    succeeded: bool,
    error: str | None = None,
    log_text: str | None = None,
) -> None:
    """Mark a Job row as succeeded or failed with a final timestamp.

    No-op if the row is already in a terminal status — this prevents the
    arq BaseException/finalizer path in render_item from clobbering a
    'cancelled' status that the cancel endpoint already set.

    On success, walks the retry_of_job_id ancestor chain and marks each
    ancestor 'superseded' so that the original failed job disappears from
    the default job list.
    """
    from ..models.job import Job  # noqa: PLC0415

    result = await db.execute(sa.select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        log.warning("finish_job: job %s not found", job_id)
        return

    # Terminal guard — do not clobber a cancel/supersede/previous finish.
    if job.status in _TERMINAL_STATUSES:
        log.debug(
            "finish_job: job %s already in terminal status %r — skipping",
            job_id,
            job.status,
        )
        return

    new_status = "succeeded" if succeeded else "failed"
    job.status = new_status
    job.progress = 100 if succeeded else job.progress
    job.finished_at = datetime.now(UTC)
    if error:
        job.error = error
    if log_text:
        job.log = log_text
    await db.flush()

    # Supersede ancestor chain when a retry/restart succeeds.
    if succeeded and job.retry_of_job_id is not None:
        await _supersede_ancestors(db, job.retry_of_job_id)


async def update_job_progress(
    db: Any,
    job_id: uuid.UUID,
    progress: int,
    log_line: str | None = None,
) -> None:
    """Update job progress (0–100) and optionally append a log line."""
    from ..models.job import Job  # noqa: PLC0415

    result = await db.execute(sa.select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        return
    job.progress = min(100, max(0, progress))
    if log_line:
        existing = job.log or ""
        job.log = (existing + "\n" + log_line).strip()
    await db.flush()
