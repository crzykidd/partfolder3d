"""Per-user "me" endpoints for Phase 3.

POST   /api/items/{key}/favorite    → star an item
DELETE /api/items/{key}/favorite    → unstar an item
GET    /api/me/favorites            → list starred items (paginated)
GET    /api/me/creations            → items whose Creator is linked to current user
GET    /api/me/path-prefix          → (deprecated) single prefix; kept for compatibility
PUT    /api/me/path-prefix          → (deprecated) single prefix; kept for compatibility
GET    /api/me/path-prefixes        → per-library × per-OS prefix map (migration 0017+)
PUT    /api/me/path-prefixes        → set per-library × per-OS prefix map (CSRF-protected)

All endpoints require authentication.
Favorites CSRF-protected on POST/DELETE; path-prefix(es) PUT is CSRF-protected.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_current_user, get_db
from ..models.creator import Creator
from ..models.favorite import Favorite
from ..models.image import Image
from ..models.item import Item
from ..models.library import Library
from ..models.tag import ItemTag, Tag
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(tags=["me"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FavoriteOut(BaseModel):
    item_id: int
    favorited: bool


class PathPrefixResponse(BaseModel):
    path_prefix: str | None


class PathPrefixRequest(BaseModel):
    path_prefix: str | None = None


class PathPrefixEntry(BaseModel):
    """Per-OS path prefix for one library."""

    windows: str | None = None
    posix: str | None = None


# Maps library_id (as string) → per-OS entry.
PathPrefixMap = dict[str, PathPrefixEntry]


class PathPrefixesResponse(BaseModel):
    """Wrapper returned by GET/PUT /api/me/path-prefixes."""

    path_prefixes: dict[str, PathPrefixEntry]


class PathPrefixesRequest(BaseModel):
    """Body accepted by PUT /api/me/path-prefixes.

    Keys are library IDs (as strings or ints).  Unknown or disabled library
    IDs are silently ignored.
    """

    path_prefixes: dict[str, PathPrefixEntry]


class ItemSummaryMini(BaseModel):
    """Minimal item summary used in me.favorites / me.creations lists."""

    id: int
    key: str
    title: str
    slug: str
    library_id: int
    dir_path: str
    created_at: datetime
    updated_at: datetime
    default_image_path: str | None = None
    creator_name: str | None = None
    tag_names: list[str] = []


class PaginatedMiniItems(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[ItemSummaryMini]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _batch_enrich(
    db: AsyncSession,
    items: list[Item],
) -> list[dict[str, Any]]:
    """Batch-load default images, tag names, and creator names for a list of items.

    Deliberately avoids accessing ORM relationships (which would trigger lazy loads
    in async context) — uses explicit batch queries keyed by FK columns instead.
    """
    if not items:
        return []
    item_ids = [i.id for i in items]

    # Default images (is_default=True takes precedence; fall back to lowest order)
    img_result = await db.execute(
        select(Image)
        .where(Image.item_id.in_(item_ids), Image.is_default.is_(True))
    )
    default_imgs: dict[int, str] = {
        img.item_id: img.path for img in img_result.scalars().all()
    }
    # Fall back: items still without a default → take lowest-order image
    missing_ids = [iid for iid in item_ids if iid not in default_imgs]
    if missing_ids:
        fb_result = await db.execute(
            select(Image)
            .where(Image.item_id.in_(missing_ids))
            .order_by(Image.item_id, Image.order)
        )
        for img in fb_result.scalars().all():
            if img.item_id not in default_imgs:
                default_imgs[img.item_id] = img.path

    # Tags
    tag_result = await db.execute(
        select(Tag.name, ItemTag.item_id)
        .join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id.in_(item_ids))
    )
    tags_by_item: dict[int, list[str]] = {}
    for name, iid in tag_result.all():
        tags_by_item.setdefault(iid, []).append(name)

    # Creator names — batch via creator_id FK to avoid async lazy-load issues
    creator_ids = list({i.creator_id for i in items if i.creator_id})
    creator_names: dict[int, str] = {}
    if creator_ids:
        c_result = await db.execute(
            select(Creator.id, Creator.name).where(Creator.id.in_(creator_ids))
        )
        creator_names = {row[0]: row[1] for row in c_result.all()}

    out = []
    for item in items:
        out.append(
            {
                "id": item.id,
                "key": item.key,
                "title": item.title,
                "slug": item.slug,
                "library_id": item.library_id,
                "dir_path": item.dir_path,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "default_image_path": default_imgs.get(item.id),
                "creator_name": creator_names.get(item.creator_id) if item.creator_id else None,
                "tag_names": tags_by_item.get(item.id, []),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


@router.post("/api/items/{key}/favorite", response_model=FavoriteOut)
async def star_item(
    key: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FavoriteOut:
    """Star (favorite) an item. Idempotent."""
    item_result = await db.execute(select(Item).where(Item.key == key))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    existing = await db.execute(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.item_id == item.id)
    )
    if existing.scalar_one_or_none() is None:
        db.add(Favorite(user_id=user.id, item_id=item.id))
        await db.flush()

    return FavoriteOut(item_id=item.id, favorited=True)


@router.delete(
    "/api/items/{key}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def unstar_item(
    key: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Unstar (un-favorite) an item. Idempotent."""
    item_result = await db.execute(select(Item).where(Item.key == key))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    fav_result = await db.execute(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.item_id == item.id)
    )
    fav = fav_result.scalar_one_or_none()
    if fav is not None:
        await db.delete(fav)
        await db.flush()


@router.get("/api/me/favorites", response_model=PaginatedMiniItems)
async def list_favorites(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> PaginatedMiniItems:
    """List the current user's starred items."""
    query = (
        select(Item)
        .join(Favorite, Favorite.item_id == Item.id)
        .where(Favorite.user_id == user.id)
    )
    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    items_result = await db.execute(
        query.order_by(Favorite.created_at.desc()).offset(offset).limit(per_page)
    )
    items = list(items_result.scalars().all())

    enriched = await _batch_enrich(db, items)
    return PaginatedMiniItems(
        total=total, page=page, per_page=per_page,
        items=[ItemSummaryMini(**d) for d in enriched],
    )


# ---------------------------------------------------------------------------
# My Creations
# ---------------------------------------------------------------------------


@router.get("/api/me/creations", response_model=PaginatedMiniItems)
async def my_creations(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> PaginatedMiniItems:
    """Items whose Creator is linked to the current user (PRD §4/§12).

    A Creator is linked to a user when the item was marked as self-designed
    (Creator.user_id == user.id).  Set via the import wizard / Add Asset in
    Phase 5; here we just query the relationship.
    """
    query = (
        select(Item)
        .join(Creator, Item.creator_id == Creator.id)
        .where(Creator.user_id == user.id)
    )
    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    items_result = await db.execute(
        query.order_by(Item.created_at.desc()).offset(offset).limit(per_page)
    )
    items = list(items_result.scalars().all())

    enriched = await _batch_enrich(db, items)
    return PaginatedMiniItems(
        total=total, page=page, per_page=per_page,
        items=[ItemSummaryMini(**d) for d in enriched],
    )


# ---------------------------------------------------------------------------
# Per-user path prefix
# ---------------------------------------------------------------------------


@router.get("/api/me/path-prefix", response_model=PathPrefixResponse)
async def get_path_prefix(
    user: Annotated[User, Depends(get_current_user)],
) -> PathPrefixResponse:
    """Get the current user's path display prefix (PRD §3.3).

    The prefix is applied client-side to rewrite the displayed dir_path so it
    matches the user's own machine/NAS mapping.  Example: user sets
    prefix = 'C:\\prints\\' so '/library/ab/ladybug-a7f3k9' displays as
    'C:\\prints\\ab\\ladybug-a7f3k9'.  The copy button copies the rewritten path.
    """
    return PathPrefixResponse(path_prefix=user.path_prefix)


@router.put("/api/me/path-prefix", response_model=PathPrefixResponse)
async def set_path_prefix(
    body: PathPrefixRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PathPrefixResponse:
    """(Deprecated) Set (or clear) the current user's legacy single path prefix.

    Use PUT /api/me/path-prefixes for the per-library × per-OS map instead.
    """
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.path_prefix = body.path_prefix
    await db.flush()
    return PathPrefixResponse(path_prefix=db_user.path_prefix)


# ---------------------------------------------------------------------------
# Per-library × per-OS path prefix map (Phase 17)
# ---------------------------------------------------------------------------


def _db_to_response(raw: Any) -> dict[str, PathPrefixEntry]:
    """Convert the raw JSONB value from the DB to the typed response dict."""
    if not raw:
        return {}
    result: dict[str, PathPrefixEntry] = {}
    for lib_id_str, entry in raw.items():
        if isinstance(entry, dict):
            result[lib_id_str] = PathPrefixEntry(
                windows=entry.get("windows"),
                posix=entry.get("posix"),
            )
    return result


@router.get("/api/me/path-prefixes", response_model=PathPrefixesResponse)
async def get_path_prefixes(
    user: Annotated[User, Depends(get_current_user)],
) -> PathPrefixesResponse:
    """Get the current user's per-library × per-OS path prefix map.

    Returns an empty dict ``{}`` when no prefixes have been configured.
    Keys are library IDs as strings; each entry has ``windows`` and ``posix``
    fields (either a path string or null).
    """
    return PathPrefixesResponse(path_prefixes=_db_to_response(user.path_prefixes))


@router.put("/api/me/path-prefixes", response_model=PathPrefixesResponse)
async def set_path_prefixes(
    body: PathPrefixesRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PathPrefixesResponse:
    """Set the current user's per-library × per-OS path prefix map (CSRF-protected).

    Only library IDs that exist in the database are persisted; unknown or
    disabled library IDs are silently ignored.  Pass an empty dict to clear
    all prefixes.  Null prefix values for a given OS are stored as-is
    (explicit "no prefix for this OS on this library").
    """
    # Validate: keep only keys whose library_id exists (enabled or not).
    lib_result = await db.execute(select(Library.id))
    valid_ids = {str(row[0]) for row in lib_result.all()}

    filtered: dict[str, Any] = {}
    for lib_id_str, entry in body.path_prefixes.items():
        if lib_id_str in valid_ids:
            filtered[lib_id_str] = {
                "windows": entry.windows,
                "posix": entry.posix,
            }

    db_result = await db.execute(select(User).where(User.id == user.id))
    db_user = db_result.scalar_one()
    db_user.path_prefixes = filtered or None
    await db.flush()

    return PathPrefixesResponse(path_prefixes=_db_to_response(db_user.path_prefixes))
