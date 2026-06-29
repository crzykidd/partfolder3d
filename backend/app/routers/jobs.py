"""Job monitor endpoints (Phase 4 — PRD §8.3).

GET  /api/jobs          → paginated list of queued/running/failed jobs (admin)
GET  /api/jobs/{id}     → single job detail (admin)
POST /api/jobs/{id}/retry → re-enqueue a failed job (admin + CSRF)

These endpoints power the admin job/queue monitor — a live view of in-flight and
recently finished background work.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..config import settings
from ..models.job import Job
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_VALID_STATUSES = {"queued", "running", "succeeded", "failed"}


class JobOut(BaseModel):
    id: str
    type: str
    status: str
    progress: int
    payload: dict[str, Any]
    log: str | None
    error: str | None
    item_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": False}


class PaginatedJobs(BaseModel):
    total: int
    page: int
    per_page: int
    jobs: list[JobOut]


class RetryOut(BaseModel):
    queued: bool


# ---------------------------------------------------------------------------
# Retry map: Job.type → (arq_task_name, callable that extracts positional args
# from the stored payload).
#
# Only "render" is retriable because it is the only job type whose arq task
# creates a Job row via create_job().  build_zip_bundle, exec_scheduled_job,
# process_import_session, and apply_review_item do NOT create Job rows, so
# no rows of those types should appear here in production.
#
# A retry does NOT reset the old failed row — it re-enqueues the arq task,
# which will create a NEW Job row when it starts.  The original failed row is
# preserved as history.
# ---------------------------------------------------------------------------

def _enqueue_args_for(job: Job) -> tuple[str, list[Any]]:
    """Return (arq_task_name, positional_args) for the given job, or raise HTTPException."""
    if job.type == "render":
        item_id = (job.payload or {}).get("item_id")
        if item_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Job payload is missing 'item_id'; cannot retry.",
            )
        return "render_item", [int(item_id)]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Job type {job.type!r} cannot be retried automatically.",
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _job_out(job: Job) -> JobOut:
    return JobOut(
        id=str(job.id),
        type=job.type,
        status=job.status,
        progress=job.progress,
        payload=job.payload or {},
        log=job.log,
        error=job.error,
        item_id=job.item_id,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedJobs)
async def list_jobs(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status: queued, running, succeeded, failed",
    ),
    job_type: str | None = Query(
        default=None,
        alias="type",
        description="Filter by job type (e.g. 'render', 'zip_bundle')",
    ),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> PaginatedJobs:
    """List background jobs, newest first.

    Useful for spotting stuck or failed jobs.
    """
    query = select(Job)

    if status_filter and status_filter in _VALID_STATUSES:
        query = query.where(Job.status == status_filter)
    if job_type:
        query = query.where(Job.type == job_type)

    count_q = sa.select(sa.func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            query.order_by(Job.created_at.desc()).offset(offset).limit(per_page)
        )
    ).scalars().all()

    return PaginatedJobs(
        total=total,
        page=page,
        per_page=per_page,
        jobs=[_job_out(j) for j in rows],
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    """Get a single job by UUID."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid job ID format (expected UUID)",
        ) from exc

    result = await db.execute(select(Job).where(Job.id == job_uuid))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return _job_out(job)


@router.post("/{job_id}/retry", response_model=RetryOut, status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RetryOut:
    """Re-enqueue a failed job.

    Only jobs in 'failed' status may be retried.  Running or queued jobs return
    409; non-retriable job types return 400.

    Behaviour: the old failed row is left intact (preserved as history).  The
    re-enqueued arq task will create a NEW Job row when it starts, exactly as it
    did on the original run.  See docs/decisions.md for the full retry map.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid job ID format (expected UUID)",
        ) from exc

    result = await db.execute(select(Job).where(Job.id == job_uuid))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only failed jobs can be retried; this job is '{job.status}'.",
        )

    task_name, task_args = _enqueue_args_for(job)

    try:
        from arq import create_pool  # noqa: PLC0415
        from arq.connections import RedisSettings  # noqa: PLC0415

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis.enqueue_job(task_name, *task_args)
        await redis.aclose()
        log.info(
            "retry_job: re-enqueued %s(%s) for failed job %s",
            task_name, task_args, job_id,
        )
        return RetryOut(queued=True)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("retry_job: failed to enqueue %s for job %s", task_name, job_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to enqueue retry: {exc}",
        ) from exc
