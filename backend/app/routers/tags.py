"""Tag browse endpoints.

GET  /api/tags              → tag list with popularity counts (drives the tag cloud + tag list)
POST /api/tags/{id}/approve → promote a pending tag to active (admin; Phase 5)

Tags are a flat popularity construct — no hierarchy.  See docs/decisions.md
"Tag tree dropped → popularity tag cloud".  The popularity count drives font-size
weighting in the UI tag cloud.  Category namespaces remain as an optional filter
facet only.

Phase 5 adds the pending-tag approval flow: import sessions create tags with
TagStatus.pending; admins approve them via POST /api/tags/{id}/approve so they
become canonical active tags visible in the cloud.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_db, require_admin
from ..models.tag import Tag, TagStatus
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tags", tags=["tags"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TagSummary(BaseModel):
    id: int
    name: str
    category: str | None
    popularity_count: int

    model_config = {"from_attributes": True}


class PaginatedTags(BaseModel):
    total: int
    page: int
    per_page: int
    tags: list[TagSummary]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedTags)
async def list_tags(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=500),
    q: str | None = Query(default=None, description="Filter by name prefix"),
    category: str | None = Query(default=None, description="Filter by category namespace"),
    active_only: bool = Query(default=True, description="Only return active tags"),
) -> PaginatedTags:
    """List tags with popularity counts, ordered by popularity desc."""
    query = select(Tag)
    if active_only:
        query = query.where(Tag.status == TagStatus.active)
    if q:
        query = query.where(Tag.name.ilike(f"%{q}%"))
    if category:
        query = query.where(Tag.category.ilike(f"{category}%"))

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        query.order_by(Tag.popularity_count.desc(), Tag.name)
        .offset(offset)
        .limit(per_page)
    )
    tags = list(result.scalars().all())

    return PaginatedTags(
        total=total,
        page=page,
        per_page=per_page,
        tags=tags,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Phase 5: pending-tag approval
# ---------------------------------------------------------------------------


class TagApproveOut(BaseModel):
    id: int
    name: str
    status: str
    category: str | None
    popularity_count: int

    model_config = {"from_attributes": True}


@router.post("/{tag_id}/approve", response_model=TagApproveOut)
async def approve_pending_tag(
    tag_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagApproveOut:
    """Promote a pending tag to active canonical status (admin only).

    Pending tags are created by the import wizard when an unknown tag string
    is encountered during reconciliation.  Admins review and approve them here
    so they become visible in the tag cloud and filterable in search.
    """
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found.")

    if tag.status == TagStatus.active:
        # Already active — idempotent
        return TagApproveOut(
            id=tag.id,
            name=tag.name,
            status=tag.status.value,
            category=tag.category,
            popularity_count=tag.popularity_count,
        )

    if tag.status != TagStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag status is '{tag.status}' — only 'pending' tags can be approved.",
        )

    tag.status = TagStatus.active
    await db.flush()

    return TagApproveOut(
        id=tag.id,
        name=tag.name,
        status=tag.status.value,
        category=tag.category,
        popularity_count=tag.popularity_count,
    )
