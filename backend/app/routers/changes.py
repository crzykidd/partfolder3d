"""Change Log endpoints — Phase 6 reconcile engine (PRD §8.3).

Admin:
  GET /api/changes → list change log entries (paginated, filterable by behavior)
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_db, require_admin
from ..models.change_log import ChangeLog
from ..models.user import User

router = APIRouter(prefix="/api/changes", tags=["changes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChangeLogOut(BaseModel):
    id: int
    behavior: str
    change_type: str
    item_id: int | None
    summary: str
    before_state: Any | None
    after_state: Any | None
    source: str
    actor: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedChanges(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[ChangeLogOut]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedChanges)
async def list_changes(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    behavior: str | None = Query(default=None),
    item_id: int | None = Query(default=None),
) -> PaginatedChanges:
    """List change log entries, newest first."""
    q = select(ChangeLog)
    if behavior:
        q = q.where(ChangeLog.behavior == behavior)
    if item_id is not None:
        q = q.where(ChangeLog.item_id == item_id)

    count_q = select(sa.func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * per_page
    rows_result = await db.execute(
        q.order_by(ChangeLog.created_at.desc()).offset(offset).limit(per_page)
    )
    rows = list(rows_result.scalars().all())

    return PaginatedChanges(
        total=total,
        page=page,
        per_page=per_page,
        items=[ChangeLogOut.model_validate(r) for r in rows],
    )
