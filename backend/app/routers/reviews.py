"""Review list endpoints — Phase 6 reconcile engine (PRD §8.2).

Admin:
  GET  /api/reviews               → list review items (pending by default)
  POST /api/reviews/{id}/approve  → approve → apply via worker
  POST /api/reviews/{id}/reject   → reject (no action taken)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.review_item import ReviewItem, ReviewStatus
from ..models.user import User

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ReviewItemOut(BaseModel):
    id: int
    behavior: str
    change_type: str
    item_id: int | None
    summary: str
    proposed_action: Any
    status: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    resolved_by_id: int | None

    model_config = {"from_attributes": True}


class PaginatedReviews(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[ReviewItemOut]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedReviews)
async def list_reviews(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default="pending", alias="status"),
    behavior: str | None = Query(default=None),
    item_id: int | None = Query(default=None),
) -> PaginatedReviews:
    """List review items.  Defaults to showing pending items only."""
    q = select(ReviewItem)
    if status_filter:
        q = q.where(ReviewItem.status == status_filter)
    if behavior:
        q = q.where(ReviewItem.behavior == behavior)
    if item_id is not None:
        q = q.where(ReviewItem.item_id == item_id)

    count_q = select(sa.func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * per_page
    rows_result = await db.execute(
        q.order_by(ReviewItem.created_at.desc()).offset(offset).limit(per_page)
    )
    rows = list(rows_result.scalars().all())

    return PaginatedReviews(
        total=total,
        page=page,
        per_page=per_page,
        items=[ReviewItemOut.model_validate(r) for r in rows],
    )


@router.post("/{review_id}/approve", response_model=ReviewItemOut)
async def approve_review(
    review_id: int,
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewItemOut:
    """Approve a pending review item.

    Enqueues the apply_review_item arq task to apply the proposed_action
    asynchronously (structural changes go through the worker).
    """
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == review_id))
    rv = result.scalar_one_or_none()
    if rv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found.")
    if rv.status != ReviewStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review item is already {rv.status!r}.",
        )

    # Mark as approved optimistically; worker will apply the action
    rv.status = ReviewStatus.approved
    rv.resolved_at = datetime.now(UTC)
    rv.resolved_by_id = admin.id
    rv.updated_at = datetime.now(UTC)
    await db.flush()

    # Enqueue the apply task
    try:
        from arq import create_pool  # noqa: I001,PLC0415
        from arq.connections import RedisSettings  # noqa: PLC0415
        from ..config import settings  # noqa: PLC0415

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis.enqueue_job("apply_review_item", rv.id)
        await redis.aclose()
    except Exception:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).exception(
            "approve_review: failed to enqueue apply_review_item for rv %s", rv.id
        )

    return ReviewItemOut.model_validate(rv)


@router.post("/{review_id}/reject", response_model=ReviewItemOut)
async def reject_review(
    review_id: int,
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewItemOut:
    """Reject a pending review item (no action taken)."""
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == review_id))
    rv = result.scalar_one_or_none()
    if rv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found.")
    if rv.status != ReviewStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review item is already {rv.status!r}.",
        )
    rv.status = ReviewStatus.rejected
    rv.resolved_at = datetime.now(UTC)
    rv.resolved_by_id = admin.id
    rv.updated_at = datetime.now(UTC)
    await db.flush()
    return ReviewItemOut.model_validate(rv)
