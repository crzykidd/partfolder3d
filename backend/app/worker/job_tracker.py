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


async def create_job(
    db: Any,
    job_type: str,
    payload: dict[str, Any],
    item_id: int | None = None,
) -> uuid.UUID:
    """Insert a new Job row in 'running' status and return its UUID."""
    from ..models.job import Job  # noqa: PLC0415

    job = Job(
        type=job_type,
        status="running",
        progress=0,
        payload=payload,
        item_id=item_id,
        started_at=datetime.now(UTC),
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job.id


async def finish_job(
    db: Any,
    job_id: uuid.UUID,
    *,
    succeeded: bool,
    error: str | None = None,
    log_text: str | None = None,
) -> None:
    """Mark a Job row as succeeded or failed with a final timestamp."""
    from ..models.job import Job  # noqa: PLC0415

    result = await db.execute(sa.select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        log.warning("finish_job: job %s not found", job_id)
        return

    job.status = "succeeded" if succeeded else "failed"
    job.progress = 100 if succeeded else job.progress
    job.finished_at = datetime.now(UTC)
    if error:
        job.error = error
    if log_text:
        job.log = log_text
    await db.flush()


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
