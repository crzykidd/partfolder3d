"""Job monitor endpoints (Phase 4 — PRD §8.3).

GET    /api/jobs                  → paginated list (admin); default excludes archived +
                                    superseded; ?archived=true → archive list only;
                                    ?include_superseded=true → show superseded rows
GET    /api/jobs/{id}             → single job detail (admin)
POST   /api/jobs/{id}/retry       → re-enqueue a failed job (admin + CSRF)
POST   /api/jobs/{id}/cancel      → cancel a running job (admin + CSRF)
POST   /api/jobs/{id}/restart     → restart a job of any status (admin + CSRF)
POST   /api/jobs/clear?status=X   → archive all non-archived jobs of a terminal status
                                    (succeeded|failed|cancelled) (admin + CSRF)
POST   /api/jobs/{id}/archive     → archive one terminal job (admin + CSRF)
DELETE /api/jobs/{id}             → hard-delete one job row (admin + CSRF)

These endpoints power the admin job/queue monitor.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import sqlalchemy as sa
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.job import Job
from ..models.user import User
from ..worker.arq_pool import get_arq_pool

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_VALID_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled", "superseded"}
_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "superseded"}


class JobOut(BaseModel):
    id: str
    type: str
    status: str
    progress: int
    payload: dict[str, Any]
    log: str | None
    error: str | None
    item_id: int | None
    retry_of_job_id: str | None
    archived_at: datetime | None
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


class ArchiveOut(BaseModel):
    archived: int


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
# preserved as history and marked 'superseded' once the new job succeeds.
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
        retry_of_job_id=str(job.retry_of_job_id) if job.retry_of_job_id else None,
        archived_at=job.archived_at,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def _resolve_job(db: AsyncSession, job_id: str) -> Job:
    """Parse UUID string, load job row, raise 422/404 on failure."""
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
    return job


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
        description="Filter by status: queued, running, succeeded, failed, cancelled, superseded",
    ),
    job_type: str | None = Query(
        default=None,
        alias="type",
        description="Filter by job type (e.g. 'render', 'zip_bundle')",
    ),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    archived: bool = Query(
        default=False,
        description="When true, return ONLY archived rows (the archive list).",
    ),
    include_superseded: bool = Query(
        default=False,
        description="When true (and archived=false), include superseded rows.",
    ),
) -> PaginatedJobs:
    """List background jobs, newest first.

    Default view excludes archived and superseded rows.
    Use archived=true for the archive list; include_superseded=true to reveal
    superseded rows in the default view.
    """
    query = select(Job)

    if archived:
        # Archive list: only rows that have been cleared/archived
        query = query.where(Job.archived_at.is_not(None))
    else:
        # Default view: exclude archived rows
        query = query.where(Job.archived_at.is_(None))
        # Exclude superseded unless the caller explicitly asks for them
        if not include_superseded:
            query = query.where(Job.status != "superseded")

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


# Terminal statuses that can be bulk-cleared (archived) by status.
_ARCHIVABLE_STATUSES = {"succeeded", "failed", "cancelled"}


@router.post("/clear", response_model=ArchiveOut)
async def clear_jobs_by_status(
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[str, Query(alias="status")],
) -> ArchiveOut:
    """Archive (set archived_at=now) all non-archived jobs of a terminal status.

    ``status`` must be one of: succeeded, failed, cancelled.  Returns the count
    archived.  422 if the status is not bulk-clearable.
    """
    if status_filter not in _ARCHIVABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot clear status {status_filter!r}. "
                f"Must be one of {sorted(_ARCHIVABLE_STATUSES)}."
            ),
        )
    now = datetime.now(UTC)
    result = await db.execute(
        select(Job).where(
            Job.status == status_filter,
            Job.archived_at.is_(None),
        )
    )
    jobs = result.scalars().all()
    for job in jobs:
        job.archived_at = now
    await db.flush()
    return ArchiveOut(archived=len(jobs))


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    """Get a single job by UUID."""
    job = await _resolve_job(db, job_id)
    return _job_out(job)


@router.post("/{job_id}/retry", response_model=RetryOut, status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> RetryOut:
    """Re-enqueue a failed job.

    Only jobs in 'failed' status may be retried.  Running or queued jobs return
    409; non-retriable job types return 400.

    Behaviour: the old failed row is left intact (preserved as history).  The
    re-enqueued arq task will create a NEW Job row when it starts, linked to
    this job via retry_of_job_id.  When the new job succeeds, the old row is
    automatically marked 'superseded'.
    """
    job = await _resolve_job(db, job_id)

    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only failed jobs can be retried; this job is '{job.status}'.",
        )

    task_name, task_args = _enqueue_args_for(job)

    try:
        await arq.enqueue_job(task_name, *task_args, retry_of_job_id=str(job.id))
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
            detail="Failed to enqueue retry.",
        ) from exc


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> JobOut:
    """Cancel a running job.

    Sets status to 'cancelled' and best-effort aborts the arq task.  The abort
    signal tells the worker to stop the task's coroutine; the task's
    BaseException handler then calls finish_job(failed), which is a no-op
    because the row is already in terminal state 'cancelled'.
    """
    job = await _resolve_job(db, job_id)

    if job.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only running jobs can be cancelled; this job is '{job.status}'.",
        )

    # Set 'cancelled' FIRST so finish_job (from the arq BaseException handler)
    # sees a terminal status and returns without clobbering our state.
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    await db.flush()

    # Best-effort abort the arq task (requires allow_abort_jobs=True on the worker).
    if job.arq_job_id:
        try:
            from arq.jobs import Job as ArqJob  # noqa: PLC0415

            await ArqJob(job.arq_job_id, arq).abort()
        except Exception:
            log.exception(
                "cancel_job: failed to abort arq job %s (non-fatal; row already cancelled)",
                job.arq_job_id,
            )

    return _job_out(job)


async def _cancel_running_job(db: AsyncSession, job: Job, arq: ArqRedis) -> None:
    """Internal: cancel a running job (no 409 check — caller has already verified intent)."""
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    await db.flush()

    if job.arq_job_id:
        try:
            from arq.jobs import Job as ArqJob  # noqa: PLC0415

            await ArqJob(job.arq_job_id, arq).abort()
        except Exception:
            log.exception(
                "_cancel_running_job: abort arq job %s failed (non-fatal)", job.arq_job_id
            )


@router.post("/{job_id}/restart", response_model=RetryOut, status_code=status.HTTP_202_ACCEPTED)
async def restart_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> RetryOut:
    """Restart a job of any status.

    If the job is currently running, it is cancelled first.  Then the work is
    re-enqueued with retry_of_job_id pointing to this job so that when the new
    run succeeds, this job row is automatically superseded.
    """
    job = await _resolve_job(db, job_id)

    # Cancel in-flight work before re-enqueueing
    if job.status == "running":
        await _cancel_running_job(db, job, arq)

    task_name, task_args = _enqueue_args_for(job)

    try:
        await arq.enqueue_job(task_name, *task_args, retry_of_job_id=str(job.id))
        log.info(
            "restart_job: re-enqueued %s(%s) for job %s (was %s)",
            task_name, task_args, job_id, job.status,
        )
        return RetryOut(queued=True)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("restart_job: failed to enqueue %s for job %s", task_name, job_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue restart.",
        ) from exc


@router.post("/{job_id}/archive", response_model=JobOut)
async def archive_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    """Archive a single terminal job by setting archived_at=now."""
    job = await _resolve_job(db, job_id)

    if job.status not in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only terminal jobs can be archived; this job is '{job.status}'.",
        )

    job.archived_at = datetime.now(UTC)
    await db.flush()
    return _job_out(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Hard-delete a job row (204 No Content)."""
    job = await _resolve_job(db, job_id)
    await db.delete(job)
    await db.flush()
