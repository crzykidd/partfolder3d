"""Review tasks — apply approved review item actions."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


async def apply_review_item(ctx: dict, review_item_id: int) -> None:
    """Apply an approved ReviewItem's proposed_action.

    Called by POST /api/reviews/{id}/approve.  Reads the ReviewItem, applies its
    proposed_action via the reconcile engine, writes a ChangeLog entry, and marks
    the ReviewItem as approved.
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.review_item import ReviewItem  # noqa: PLC0415
    from app.worker.reconcile import apply_review_item_action  # noqa: PLC0415

    async with SessionLocal() as db:
        result = await db.execute(
            sa.select(ReviewItem).where(ReviewItem.id == review_item_id)
        )
        rv = result.scalar_one_or_none()
        if rv is None:
            log.warning("apply_review_item: review_item %s not found", review_item_id)
            return
        await apply_review_item_action(db, rv)
        await db.commit()
    log.info("apply_review_item: review_item %s applied and approved", review_item_id)
