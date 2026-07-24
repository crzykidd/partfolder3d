"""Review list endpoints — Phase 6 reconcile engine (PRD §8.2).

Admin:
  GET  /api/reviews               → list review items (pending by default)
  POST /api/reviews/{id}/approve  → approve → apply via worker
  POST /api/reviews/{id}/reject   → reject (no action taken)
  POST /api/reviews/approve-all   → approve every pending item → apply via worker (N jobs)
  POST /api/reviews/reject-all    → reject every pending item (pure status flip)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import sqlalchemy as sa
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.review_item import ReviewItem, ReviewStatus
from ..models.user import User
from ..worker.arq_pool import get_arq_pool

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


class ApproveAllReviewsResponse(BaseModel):
    approved: int


class RejectAllReviewsResponse(BaseModel):
    rejected: int


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


@router.post(
    "/approve-all",
    response_model=ApproveAllReviewsResponse,
    summary="Approve all pending review items",
)
async def approve_all_reviews(
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> ApproveAllReviewsResponse:
    """Approve every ``pending`` review item and enqueue its apply job.

    Unlike ``reject-all`` this replays real work: each approved row enqueues
    the same ``apply_review_item`` arq task the singular approve endpoint
    uses, so N pending items means N applied mutations against the library.
    Idempotent: with zero pending items this returns 200 with ``approved: 0``.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        sa.update(ReviewItem)
        .where(ReviewItem.status == ReviewStatus.pending)
        .values(
            status=ReviewStatus.approved,
            resolved_at=now,
            resolved_by_id=admin.id,
            updated_at=now,
        )
        .returning(ReviewItem.id)
    )
    review_ids = [row[0] for row in result.all()]
    await db.flush()

    for review_id in review_ids:
        try:
            await arq.enqueue_job("apply_review_item", review_id)
        except Exception:
            import logging  # noqa: PLC0415
            logging.getLogger(__name__).exception(
                "approve_all_reviews: failed to enqueue apply_review_item for rv %s", review_id
            )

    return ApproveAllReviewsResponse(approved=len(review_ids))


@router.post(
    "/reject-all",
    response_model=RejectAllReviewsResponse,
    summary="Reject all pending review items",
)
async def reject_all_reviews(
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RejectAllReviewsResponse:
    """Reject every ``pending`` review item — a pure status flip, no action taken.

    Idempotent: with zero pending items this returns 200 with ``rejected: 0``.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        sa.update(ReviewItem)
        .where(ReviewItem.status == ReviewStatus.pending)
        .values(
            status=ReviewStatus.rejected,
            resolved_at=now,
            resolved_by_id=admin.id,
            updated_at=now,
        )
    )
    rejected = result.rowcount or 0
    await db.flush()
    return RejectAllReviewsResponse(rejected=rejected)


@router.post("/{review_id}/approve", response_model=ReviewItemOut)
async def approve_review(
    review_id: int,
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
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
        await arq.enqueue_job("apply_review_item", rv.id)
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
