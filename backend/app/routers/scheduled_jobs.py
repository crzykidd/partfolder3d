"""Scheduled-jobs API (Phase 4 — PRD §8.4).

GET  /api/scheduled-jobs           → list recurring jobs (last/next/running)
POST /api/scheduled-jobs/{name}/run → enqueue a job immediately (run-now)

Admin-only.  These endpoints power the Scheduled Jobs view in the admin UI.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.scheduled_job import ScheduledJob
from ..models.user import User
from ..worker.arq_pool import get_arq_pool

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduled-jobs", tags=["scheduled-jobs"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ScheduledJobOut(BaseModel):
    name: str
    description: str
    schedule: str
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_error: str | None
    next_run_at: datetime | None
    is_running: bool

    model_config = {"from_attributes": True}


class RunNowResponse(BaseModel):
    enqueued: bool
    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ScheduledJobOut])
async def list_scheduled_jobs(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ScheduledJobOut]:
    """List all registered recurring jobs with their last/next/running state."""
    result = await db.execute(select(ScheduledJob).order_by(ScheduledJob.name))
    jobs = result.scalars().all()
    return [ScheduledJobOut.model_validate(j) for j in jobs]


@router.post("/{name}/run", response_model=RunNowResponse)
async def run_now(
    name: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> RunNowResponse:
    """Enqueue a named scheduled job immediately, independent of its schedule.

    The job runs as an arq task on the worker.  Returns 404 if the name is not
    registered.
    """
    # Validate name against the DB (seeded from the registry at worker startup)
    result = await db.execute(
        select(ScheduledJob).where(ScheduledJob.name == name)
    )
    sj = result.scalar_one_or_none()
    if sj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduled job {name!r} not found.",
        )

    # Enqueue via the shared arq pool
    try:
        await arq.enqueue_job("exec_scheduled_job", name)
        return RunNowResponse(enqueued=True, message=f"Job {name!r} enqueued.")
    except Exception as exc:
        log.exception("run_now: failed to enqueue %r", name)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue job.",
        ) from exc
