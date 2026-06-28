"""Job monitor endpoints (Phase 4 — PRD §8.3).

GET  /api/jobs          → paginated list of queued/running/failed jobs (admin)
GET  /api/jobs/{id}     → single job detail (admin)

These endpoints power the admin job/queue monitor — a live view of in-flight and
recently finished background work.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_db, require_admin
from ..models.job import Job
from ..models.user import User

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
