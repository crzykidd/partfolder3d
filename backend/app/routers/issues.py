"""Issues endpoints — Phase 6 reconcile engine (PRD §8.3).

Admin:
  GET  /api/issues           → list issues (filter by status/type, paginate)
  GET  /api/issues/{id}      → issue detail
  POST /api/issues/{id}/resolve → mark resolved
  POST /api/issues/{id}/ignore  → mark ignored
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.issue import Issue, IssueStatus
from ..models.user import User

router = APIRouter(prefix="/api/issues", tags=["issues"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class IssueOut(BaseModel):
    id: int
    issue_type: str
    severity: str
    status: str
    item_id: int | None
    detail: str
    suggested_action: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class PaginatedIssues(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[IssueOut]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedIssues)
async def list_issues(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    issue_type: str | None = Query(default=None),
    item_id: int | None = Query(default=None),
) -> PaginatedIssues:
    """List issues with optional filtering."""
    q = select(Issue)
    if status_filter:
        q = q.where(Issue.status == status_filter)
    if issue_type:
        q = q.where(Issue.issue_type == issue_type)
    if item_id is not None:
        q = q.where(Issue.item_id == item_id)

    count_q = select(sa.func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * per_page
    rows_result = await db.execute(
        q.order_by(Issue.created_at.desc()).offset(offset).limit(per_page)
    )
    rows = list(rows_result.scalars().all())

    return PaginatedIssues(
        total=total,
        page=page,
        per_page=per_page,
        items=[IssueOut.model_validate(r) for r in rows],
    )


@router.get("/{issue_id}", response_model=IssueOut)
async def get_issue(
    issue_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IssueOut:
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")
    return IssueOut.model_validate(issue)


@router.post("/{issue_id}/resolve", response_model=IssueOut)
async def resolve_issue(
    issue_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IssueOut:
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")
    issue.status = IssueStatus.resolved
    issue.resolved_at = datetime.now(UTC)
    issue.updated_at = datetime.now(UTC)
    await db.flush()
    return IssueOut.model_validate(issue)


@router.post("/{issue_id}/ignore", response_model=IssueOut)
async def ignore_issue(
    issue_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IssueOut:
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")
    issue.status = IssueStatus.ignored
    issue.updated_at = datetime.now(UTC)
    await db.flush()
    return IssueOut.model_validate(issue)
