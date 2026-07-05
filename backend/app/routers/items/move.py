"""Move item asset(s) between libraries — single + bulk (issue #25).

POST /api/items/{key}/move   → move one item to another library (auth required)
POST /api/items/move         → bulk-move a set of items to another library (auth)

The heavy lifting (copy → verify-hash → remove, interrupted-safe) lives in
``storage.library_move.move_item_to_library``.  This router coordinates the DB side:
it relocates the on-disk directory, updates ``library_id`` + ``dir_path``, re-inventories
the File rows, and rewrites the sidecar at the new path — all in one transaction per item.

Bulk is **N independent per-item transactions** (own ``SessionLocal`` each, mirroring the
bulk-import commit path): one item failing never rolls back or corrupts the others.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...auth.deps import csrf_protect, get_current_user, get_db
from ...models.creator import Creator
from ...models.file import File
from ...models.image import Image
from ...models.item import Item
from ...models.library import Library
from ...models.tag import ItemTag, Tag
from ...models.user import User
from ...services.item_helpers import _write_item_sidecar
from ...storage.inventory import inventory_item
from ...storage.library_move import LibraryMoveError, move_item_to_library
from ...storage.paths import item_dir_path, sidecar_name
from ...storage.ssrf_guard import sanitize_for_log
from .helpers import _build_item_detail

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["items"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MoveItemRequest(BaseModel):
    target_library_id: int


class BulkMoveRequest(BaseModel):
    keys: list[str]
    target_library_id: int


class BulkMoveSkipped(BaseModel):
    key: str
    reason: str


class BulkMoveResponse(BaseModel):
    total: int
    moved: int
    skipped: list[BulkMoveSkipped]
    errors: list[BulkMoveSkipped]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _resolve_target_library(
    target_library_id: int, source_library_id: int, db: AsyncSession
) -> Library:
    """Load + validate the destination library (enabled, exists, different).

    Raises HTTPException on any validation failure.
    """
    if target_library_id == source_library_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target library is the same as the item's current library.",
        )
    result = await db.execute(
        select(Library).where(Library.id == target_library_id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library {target_library_id} not found.",
        )
    if not target.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Library {target_library_id} is disabled.",
        )
    return target


async def _resync_item_files(db: AsyncSession, item: Item, new_dir: Path) -> None:
    """Re-inventory *new_dir* and reconcile the item's File rows.

    Relative paths are stable across a library move (only the mount root changes),
    so this is normally a no-op beyond refreshing size/mtime/hash snapshots.  It is
    still run for correctness — it detects any stray/removed file at the new path.
    Existing rows are updated in place (preserving Phase-16 ``object_analysis``).
    """
    file_result = await db.execute(select(File).where(File.item_id == item.id))
    db_files = list(file_result.scalars().all())
    by_path = {f.path: f for f in db_files}
    existing = {
        f.path: (f.last_seen_size, f.last_seen_mtime or f.mtime, f.sha256)
        for f in db_files
    }

    sc_name = sidecar_name(item.title, item.key)
    records = inventory_item(new_dir, sc_name, existing=existing)
    disk_paths = {r.relative_path for r in records}

    for rec in records:
        row = by_path.get(rec.relative_path)
        if row is None:
            db.add(File(
                item_id=item.id,
                path=rec.relative_path,
                role=rec.role,
                size=rec.size,
                sha256=rec.sha256,
                mtime=rec.mtime,
                last_seen_size=rec.size,
                last_seen_mtime=rec.mtime,
            ))
        else:
            row.role = rec.role
            row.size = rec.size
            row.sha256 = rec.sha256
            row.mtime = rec.mtime
            row.last_seen_size = rec.size
            row.last_seen_mtime = rec.mtime

    # Drop rows whose file no longer exists at the new path.
    for row in db_files:
        if row.path not in disk_paths:
            await db.delete(row)

    await db.flush()


async def _move_one_item(db: AsyncSession, item: Item, target: Library) -> None:
    """Move *item* to *target* library: relocate files, update DB, re-inventory.

    Assumes the target has already been validated (enabled, different).  Runs inside
    the caller's transaction — the caller commits (or rolls back) per item.

    Raises:
        LibraryMoveError: if the on-disk move fails (source left intact).
    """
    src_dir = Path(item.dir_path)
    dst_dir = item_dir_path(target.mount_path, item.key, item.title)

    # Filesystem move (copy → verify → remove).  Source stays intact until verified.
    move_item_to_library(src_dir, dst_dir, item.key)

    # DB: point the row at the new library + path.
    item.library_id = target.id
    item.dir_path = str(dst_dir)
    item.updated_at = datetime.now(UTC)
    await db.flush()

    # Re-inventory File rows at the new location, then rewrite the sidecar there.
    await _resync_item_files(db, item, dst_dir)
    await _write_item_sidecar(db, item)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/move", response_model=BulkMoveResponse)
async def bulk_move_items(
    body: BulkMoveRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkMoveResponse:
    """Move multiple items to another library (partial-success, per-item isolation).

    Each item is moved in its own transaction (its own ``SessionLocal``) so a failure
    on one — a locked file, a hash mismatch, a bad key — fails only that item and never
    rolls back the ones already moved.
    """
    from ...db import SessionLocal  # noqa: PLC0415

    moved = 0
    skipped: list[BulkMoveSkipped] = []
    errors: list[BulkMoveSkipped] = []

    # De-duplicate keys while preserving order.
    seen: set[str] = set()
    keys = [k for k in body.keys if not (k in seen or seen.add(k))]

    for key in keys:
        async with SessionLocal() as iso_db:
            try:
                result = await iso_db.execute(
                    select(Item)
                    .options(selectinload(Item.creator))
                    .where(Item.key == key)
                )
                item = result.scalar_one_or_none()
                if item is None:
                    skipped.append(BulkMoveSkipped(key=key, reason="not_found"))
                    continue

                if item.library_id == body.target_library_id:
                    skipped.append(BulkMoveSkipped(key=key, reason="same_library"))
                    continue

                target = await _resolve_target_library(
                    body.target_library_id, item.library_id, iso_db
                )

                await _move_one_item(iso_db, item, target)
                await iso_db.commit()
                moved += 1
            except HTTPException as exc:
                await _safe_rollback(iso_db)
                skipped.append(BulkMoveSkipped(key=key, reason=str(exc.detail)[:200]))
            except LibraryMoveError as exc:
                await _safe_rollback(iso_db)
                _safe_key = key.replace("\r", "\\r").replace("\n", "\\n")
                log.warning("bulk_move: move failed for item %s: %s", _safe_key, exc)
                errors.append(BulkMoveSkipped(key=key, reason=str(exc)[:200]))
            except Exception as exc:
                await _safe_rollback(iso_db)
                _safe_key = key.replace("\r", "\\r").replace("\n", "\\n")
                log.exception("bulk_move: unexpected error on item %s", _safe_key)
                errors.append(BulkMoveSkipped(key=key, reason=str(exc)[:200]))

    return BulkMoveResponse(
        total=len(keys), moved=moved, skipped=skipped, errors=errors
    )


@router.post("/{key}/move", response_model=None)
async def move_item(
    key: str,
    body: MoveItemRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Move a single item to another library."""
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    target = await _resolve_target_library(body.target_library_id, item.library_id, db)

    try:
        await _move_one_item(db, item, target)
    except LibraryMoveError as exc:
        log.warning("move_item: move failed for item %s: %s", sanitize_for_log(key), exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed to move item directory to the target library.",
        ) from exc

    # Load response data.
    tag_result = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = list(tag_result.scalars().all())

    file_result = await db.execute(select(File).where(File.item_id == item.id))
    files = list(file_result.scalars().all())
    img_result = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images = list(img_result.scalars().all())
    if item.creator_id and not item.creator:
        creator_result = await db.execute(
            select(Creator).where(Creator.id == item.creator_id)
        )
        item.creator = creator_result.scalar_one_or_none()

    return _build_item_detail(item, tags, files, images)


async def _safe_rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception:
        pass
