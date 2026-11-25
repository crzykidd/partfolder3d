"""Bulk item actions for catalog multi-select — tags / delete / rescan.

POST /api/items/bulk-tags     → add and/or remove tags across many items
POST /api/items/bulk-delete   → move many items to trash (same as DELETE /{key})
POST /api/items/bulk-rescan   → per-item reconcile for many items (max 100)

(``bulk-print-records`` lives in ``routers/print_records.py``; bulk *move* in ``move.py``.)

All are partial-success with per-item isolation: each item runs in its own
``SessionLocal`` transaction (mirroring bulk move), so one failure never rolls back the
others.  Single-segment paths on purpose — ``/bulk/rescan`` would be captured by
``POST /{key}/rescan``.
"""

from __future__ import annotations

import logging
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...auth.deps import csrf_protect, get_current_user
from ...models.item import Item
from ...models.tag import ItemTag, Tag
from ...models.user import User
from ...services.item_helpers import (
    _add_remove_tags,
    _enqueue_analyze,
    _resolve_new_tag_status,
    _update_search_vector,
    _write_item_sidecar,
)
from ...storage.ssrf_guard import sanitize_for_log
from ...worker.arq_pool import get_arq_pool
from .core import _trash_and_delete_item
from .schemas import (
    BulkItemFailure,
    BulkItemResult,
    BulkKeysRequest,
    BulkRescanRequest,
    BulkTagsRequest,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["items"])


async def _safe_rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception:
        pass


def _err_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)[:200]
    return (str(exc) or exc.__class__.__name__)[:200]


async def _run_per_item(keys: list[str], label: str, op) -> BulkItemResult:
    """Run ``op(db, item)`` for each key in its own session/transaction."""
    from ...db import SessionLocal  # noqa: PLC0415

    succeeded: list[str] = []
    failed: list[BulkItemFailure] = []
    for key in keys:
        async with SessionLocal() as iso_db:
            try:
                result = await iso_db.execute(
                    select(Item).options(selectinload(Item.creator)).where(Item.key == key)
                )
                item = result.scalar_one_or_none()
                if item is None:
                    failed.append(BulkItemFailure(key=key, error="Item not found."))
                    continue
                await op(iso_db, item)
                await iso_db.commit()
                succeeded.append(key)
            except HTTPException as exc:
                await _safe_rollback(iso_db)
                failed.append(BulkItemFailure(key=key, error=_err_text(exc)))
            except Exception as exc:
                await _safe_rollback(iso_db)
                log.exception("%s: unexpected error on item %s", label, sanitize_for_log(key))
                failed.append(BulkItemFailure(key=key, error=_err_text(exc)))
    return BulkItemResult(succeeded=succeeded, failed=failed)


@router.post("/bulk-tags", response_model=BulkItemResult)
async def bulk_tags(
    body: BulkTagsRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
) -> BulkItemResult:
    """Add and/or remove tags on many items (add/remove semantics, NOT replace).

    New set per item = (current - remove) | add.  Brand-new tag names land ``pending``
    unless ``tags.auto_approve`` is on, like ``PATCH /{key}``.  Write-through matches
    PATCH: DB + sidecar + search vector.  Items whose tags don't change count as
    succeeded.
    """

    async def op(db: AsyncSession, item: Item) -> None:
        new_status = await _resolve_new_tag_status(db)
        changed = await _add_remove_tags(
            db, item, body.add, body.remove, new_tag_status=new_status
        )
        if not changed:
            return
        from datetime import UTC, datetime  # noqa: PLC0415

        item.updated_at = datetime.now(UTC)
        await db.flush()
        await _write_item_sidecar(db, item)
        tag_result = await db.execute(
            select(Tag.name).join(ItemTag, Tag.id == ItemTag.tag_id)
            .where(ItemTag.item_id == item.id)
        )
        await _update_search_vector(
            db, item.id, item.title, item.description, list(tag_result.scalars().all())
        )

    return await _run_per_item(body.keys, "bulk_tags", op)


@router.post("/bulk-delete", response_model=BulkItemResult)
async def bulk_delete(
    body: BulkKeysRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
) -> BulkItemResult:
    """Move many items to trash and delete their rows (same semantics as DELETE /{key})."""

    async def op(db: AsyncSession, item: Item) -> None:
        await _trash_and_delete_item(db, item)

    return await _run_per_item(body.keys, "bulk_delete", op)


@router.post("/bulk-rescan", response_model=BulkItemResult)
async def bulk_rescan(
    body: BulkRescanRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> BulkItemResult:
    """Rescan many items inline, sequentially (max 100), same engine as ``/{key}/rescan``."""
    from ...worker.reconcile import load_mode_settings, reconcile_one_item  # noqa: PLC0415

    async def op(db: AsyncSession, item: Item) -> None:
        mode_settings = await load_mode_settings(db)
        mode_settings = {**mode_settings, "file_changes": "auto", "sidecar_sync": "auto"}
        await reconcile_one_item(
            db,
            item,
            mode_settings=mode_settings,
            url_validator=None,
            source="per_item_rescan",
        )
        await _enqueue_analyze(item.id, pool=arq, db=db)

    return await _run_per_item(body.keys, "bulk_rescan", op)
