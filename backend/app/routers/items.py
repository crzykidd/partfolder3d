"""Item CRUD endpoints.

POST   /api/items                       → create item (auth required)
GET    /api/items                       → list items (paginated, searchable, filterable)
GET    /api/items/{key}                 → item detail
PATCH  /api/items/{key}                 → update metadata; title change = atomic rename
DELETE /api/items/{key}                 → move to trash (auth required)
POST   /api/items/{key}/rescan          → re-inventory + re-sync sidecar (auth required)
PATCH  /api/items/{key}/default-image   → set default image (Phase 3)

Phase 3 additions to GET /api/items:
  q          — full-text search (title + description + tags via tsvector + GIN index)
  tags       — AND-filter by tag names (repeat param)
  creator_id — filter by creator
  favorited  — if true, only items starred by current user (requires auth)
  sort       — created_at_desc (default), created_at_asc, updated_at_desc,
               title_asc, title_desc, relevance (only with q)

Auth:  item writes require get_current_user.
       No admin-only gate on item operations (all authenticated users can write).
       Library management is admin-only (see libraries.py).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.deps import csrf_protect, get_current_user, get_db, get_optional_user
from ..config import settings
from ..models.creator import Creator
from ..models.favorite import Favorite
from ..models.file import File, FileRole
from ..models.image import Image
from ..models.item import Item
from ..models.library import Library
from ..models.tag import ItemTag, Tag
from ..models.user import User
from ..storage.inventory import FileRecord, inventory_item
from ..storage.journal import MoveError, atomic_rename, move_to_trash
from ..storage.keys import generate_unique_key
from ..storage.paths import item_dir_path, item_slug, sidecar_name
from ..storage.sidecar import SidecarFile, SidecarImage, build_sidecar, write_sidecar
from ..worker.render_mesh import MESH_EXTENSIONS

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["items"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreatorIn(BaseModel):
    name: str
    profile_url: str | None = None
    source_site: str | None = None


class TagIn(BaseModel):
    name: str


class ItemCreate(BaseModel):
    title: str
    library_id: int
    description: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    license: str | None = None
    creator: CreatorIn | None = None
    tags: list[str] = []


class ItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    license: str | None = None
    creator: CreatorIn | None = None
    tags: list[str] | None = None


class CreatorOut(BaseModel):
    id: int
    name: str
    profile_url: str | None
    source_site: str | None

    model_config = {"from_attributes": True}


class FileOut(BaseModel):
    id: int
    path: str
    role: str
    size: int
    sha256: str | None

    model_config = {"from_attributes": True}


class ImageOut(BaseModel):
    id: int
    path: str
    source: str
    is_default: bool
    order: int

    model_config = {"from_attributes": True}


class TagOut(BaseModel):
    id: int
    name: str
    category: str | None

    model_config = {"from_attributes": True}


class SetDefaultImageRequest(BaseModel):
    image_id: int


class ItemSummary(BaseModel):
    id: int
    key: str
    title: str
    slug: str
    library_id: int
    dir_path: str
    created_at: datetime
    updated_at: datetime
    # Phase 3 additions: enriched catalog data (default None for backward compat)
    default_image_path: str | None = None
    creator_name: str | None = None
    tag_names: list[str] = []
    favorited: bool = False

    model_config = {"from_attributes": False}


class ItemDetail(BaseModel):
    id: int
    key: str
    title: str
    slug: str
    library_id: int
    dir_path: str
    created_at: datetime
    updated_at: datetime
    description: str | None
    source_url: str | None
    source_site: str | None
    license: str | None
    schema_version: int
    creator: CreatorOut | None
    tags: list[TagOut]
    files: list[FileOut]
    images: list[ImageOut]

    model_config = {"from_attributes": True}


class PaginatedItems(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[ItemSummary]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_or_create_tag(db: AsyncSession, name: str) -> Tag:
    """Get a tag by name or create it if absent."""
    result = await db.execute(select(Tag).where(Tag.name == name))
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name)
        db.add(tag)
        await db.flush()
    return tag


async def _attach_tags(db: AsyncSession, item: Item, tag_names: list[str]) -> None:
    """Replace the item's tags with the given list."""
    # Remove existing
    await db.execute(
        ItemTag.__table__.delete().where(ItemTag.item_id == item.id)  # type: ignore[attr-defined]
    )
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        tag = await _get_or_create_tag(db, name)
        db.add(ItemTag(item_id=item.id, tag_id=tag.id))
    await db.flush()


async def _update_search_vector(
    db: AsyncSession,
    item_id: int,
    title: str,
    description: str | None,
    tag_names: list[str],
) -> None:
    """Maintain the items.search_vector tsvector column.

    The vector is built from title (weighted A), description (weighted B), and
    tag names (weighted C) so title matches rank highest.  Called after any write
    that changes these fields.

    Uses raw SQL to avoid SQLAlchemy type-mapping complexity with TSVECTOR.
    """
    parts: list[str] = [title]
    if description:
        parts.append(description)
    if tag_names:
        parts.append(" ".join(tag_names))
    combined = " ".join(parts)
    await db.execute(
        sa.text(
            "UPDATE items SET search_vector = to_tsvector('english', :text)"
            " WHERE id = :id"
        ),
        {"text": combined, "id": item_id},
    )


async def _build_sidecar_data(
    db: AsyncSession,
    item: Item,
) -> tuple[list[str], list[SidecarFile], list[SidecarImage], str | None]:
    """Return (tag_names, sidecar_files, sidecar_images, default_image_path)."""
    tag_result = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = [t.name for t in tag_result.scalars().all()]

    file_result = await db.execute(
        select(File).where(File.item_id == item.id)
    )
    sidecar_files = [
        SidecarFile(
            path=f.path,
            role=f.role.value,
            size=f.size,
            sha256=f.sha256,
            mtime=f.mtime.strftime("%Y-%m-%dT%H:%M:%SZ") if f.mtime else None,
        )
        for f in file_result.scalars().all()
    ]

    img_result = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images_list = img_result.scalars().all()
    sidecar_images = [
        SidecarImage(path=img.path, source=img.source.value, order=img.order)
        for img in images_list
    ]
    default_img = next((img.path for img in images_list if img.is_default), None)

    return tags, sidecar_files, sidecar_images, default_img


async def _write_item_sidecar(db: AsyncSession, item: Item) -> None:
    """Write (or overwrite) the sidecar for an item."""
    tags, files, images, default_img = await _build_sidecar_data(db, item)
    data = build_sidecar(
        item, tags=tags, files=files, images=images, default_image=default_img
    )
    item_dir = Path(item.dir_path)
    write_sidecar(item_dir, data, item.title, item.key)


def _apply_file_records(
    item: Item,
    records: list[FileRecord],
    db_files: list[File],
) -> tuple[list[File], list[File]]:
    """Merge inventory records with existing DB File rows.

    Returns (files_to_upsert, files_to_delete).
    """
    existing_by_path: dict[str, File] = {f.path: f for f in db_files}
    disk_paths = {r.relative_path for r in records}

    to_delete = [f for path, f in existing_by_path.items() if path not in disk_paths]

    to_upsert: list[File] = []
    for rec in records:
        if rec.relative_path in existing_by_path:
            f = existing_by_path[rec.relative_path]
            f.size = rec.size
            f.sha256 = rec.sha256
            f.mtime = rec.mtime
            f.role = rec.role
            f.last_seen_size = rec.size
            f.last_seen_mtime = rec.mtime
        else:
            f = File(
                item_id=item.id,
                path=rec.relative_path,
                role=rec.role,
                size=rec.size,
                sha256=rec.sha256,
                mtime=rec.mtime,
                last_seen_size=rec.size,
                last_seen_mtime=rec.mtime,
            )
        to_upsert.append(f)

    return to_upsert, to_delete


async def _enqueue_render(item_id: int) -> None:
    """Fire-and-forget: enqueue a render_item arq task for an item.

    Failure to enqueue (e.g. Redis not available) is logged but does NOT
    propagate — it must never block item creation or rescan.
    """
    try:
        from arq import create_pool  # noqa: PLC0415
        from arq.connections import RedisSettings  # noqa: PLC0415

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis.enqueue_job("render_item", item_id)
        await redis.aclose()
        log.debug("_enqueue_render: render_item enqueued for item %s", item_id)
    except Exception:
        log.exception("_enqueue_render: failed to enqueue render for item %s", item_id)


def _build_item_detail(
    item: Item,
    tags: list[Tag],
    files: list[File],
    images: list[Image],
) -> dict[str, Any]:
    """Build the ItemDetail dict from loaded ORM objects."""
    return {
        "id": item.id,
        "key": item.key,
        "title": item.title,
        "slug": item.slug,
        "library_id": item.library_id,
        "dir_path": item.dir_path,
        "description": item.description,
        "source_url": item.source_url,
        "source_site": item.source_site,
        "license": item.license,
        "schema_version": item.schema_version,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "creator": item.creator,
        "tags": tags,
        "files": files,
        "images": images,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=ItemDetail, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Create a new item: assign key, create dir, write sidecar, inventory files."""
    # Validate library
    lib_result = await db.execute(
        select(Library).where(Library.id == body.library_id, Library.enabled.is_(True))
    )
    library = lib_result.scalar_one_or_none()
    if library is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library {body.library_id} not found or not enabled.",
        )

    # Generate unique key
    key = await generate_unique_key(db)
    slug = item_slug(body.title, key)

    # Resolve or create creator
    creator: Creator | None = None
    if body.creator:
        creator = Creator(
            name=body.creator.name,
            profile_url=body.creator.profile_url,
            source_site=body.creator.source_site,
        )
        db.add(creator)
        await db.flush()

    # Create the on-disk directory
    item_dir = item_dir_path(library.mount_path, key, body.title)
    item_dir.mkdir(parents=True, exist_ok=True)

    # Insert Item row
    item = Item(
        key=key,
        title=body.title,
        slug=slug,
        description=body.description,
        source_url=body.source_url,
        source_site=body.source_site,
        license=body.license,
        creator_id=creator.id if creator else None,
        library_id=body.library_id,
        dir_path=str(item_dir),
        schema_version=1,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)

    # Attach tags
    if body.tags:
        await _attach_tags(db, item, body.tags)

    # Inventory existing files in the dir (usually empty on create)
    sc_name = sidecar_name(body.title, key)
    records = inventory_item(item_dir, sc_name)
    file_objs: list[File] = []
    for rec in records:
        f = File(
            item_id=item.id,
            path=rec.relative_path,
            role=rec.role,
            size=rec.size,
            sha256=rec.sha256,
            mtime=rec.mtime,
            last_seen_size=rec.size,
            last_seen_mtime=rec.mtime,
        )
        db.add(f)
        file_objs.append(f)

    await db.flush()

    # Load creator for sidecar
    if creator:
        await db.refresh(creator)
        item.creator = creator

    # Write sidecar
    await _write_item_sidecar(db, item)

    # Load tags for response
    tag_result = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = list(tag_result.scalars().all())

    img_result = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images = list(img_result.scalars().all())

    # Update full-text search vector
    await _update_search_vector(
        db, item.id, item.title, item.description, [t.name for t in tags]
    )

    # Phase 4: enqueue render job (fire-and-forget; never blocks item creation)
    await _enqueue_render(item.id)

    return _build_item_detail(item, tags, file_objs, images)


_VALID_SORTS = {
    "created_at_desc",
    "created_at_asc",
    "updated_at_desc",
    "title_asc",
    "title_desc",
    "relevance",
}


def _sort_clause(sort: str, q: str | None) -> Any:
    """Return the ORDER BY clause for the given sort key."""
    if sort == "relevance" and q:
        tsq = func.websearch_to_tsquery(sa.literal("english"), q)
        return func.ts_rank(Item.search_vector, tsq).desc()
    if sort == "created_at_asc":
        return Item.created_at.asc()
    if sort == "updated_at_desc":
        return Item.updated_at.desc()
    if sort == "title_asc":
        return Item.title.asc()
    if sort == "title_desc":
        return Item.title.desc()
    return Item.created_at.desc()  # default: created_at_desc


@router.get("", response_model=PaginatedItems)
async def list_items(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    library_id: int | None = Query(default=None),
    # Phase 3 search / filter params
    q: str | None = Query(default=None, description="Full-text search (title/description/tags)"),
    tags: list[str] | None = Query(
        default=None,
        description="AND-filter by tag names (repeat for multiple)",
    ),
    creator_id: int | None = Query(default=None, description="Filter by creator id"),
    favorited: bool | None = Query(
        default=None, description="If true, only return current user's favorites"
    ),
    sort: str = Query(
        default="created_at_desc",
        description=f"Sort order: {', '.join(sorted(_VALID_SORTS))}",
    ),
) -> PaginatedItems:
    """List items (paginated, searchable, filterable).

    Filters are AND-combined.  `favorited=true` requires authentication; without it
    the filter is ignored.  `sort=relevance` requires `q`; without it falls back to
    `created_at_desc`.
    """
    if sort not in _VALID_SORTS:
        sort = "created_at_desc"

    query = select(Item).options(selectinload(Item.creator))
    if library_id is not None:
        query = query.where(Item.library_id == library_id)

    # Full-text search
    params: dict[str, Any] = {}
    if q:
        query = query.where(
            sa.text(
                "items.search_vector @@ websearch_to_tsquery('english', :fts_q)"
            ).bindparams(sa.bindparam("fts_q", q))
        )
        params["fts_q"] = q

    # Tag filter (AND semantics using HAVING COUNT)
    if tags:
        clean_tags = [t.strip() for t in tags if t.strip()]
        if clean_tags:
            tag_subq = (
                select(ItemTag.item_id)
                .join(Tag, Tag.id == ItemTag.tag_id)
                .where(Tag.name.in_(clean_tags))
                .group_by(ItemTag.item_id)
                .having(func.count(sa.func.distinct(Tag.id)) == len(clean_tags))
            ).scalar_subquery()
            query = query.where(Item.id.in_(tag_subq))

    # Creator filter
    if creator_id is not None:
        query = query.where(Item.creator_id == creator_id)

    # Favorites filter (only if user is authenticated)
    if favorited is True and user is not None:
        query = query.join(Favorite, sa.and_(
            Favorite.item_id == Item.id,
            Favorite.user_id == user.id,
        ))

    # Count (same filters, no pagination)
    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q, params)
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    items_result = await db.execute(
        query.order_by(_sort_clause(sort, q)).offset(offset).limit(per_page),
        params,
    )
    items = list(items_result.scalars().all())

    if not items:
        return PaginatedItems(total=total, page=page, per_page=per_page, items=[])

    item_ids = [i.id for i in items]

    # Batch-load default images
    img_result = await db.execute(
        select(Image).where(Image.item_id.in_(item_ids), Image.is_default.is_(True))
    )
    default_imgs: dict[int, str] = {
        img.item_id: img.path for img in img_result.scalars().all()
    }
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

    # Batch-load tag names
    tag_result = await db.execute(
        select(Tag.name, ItemTag.item_id)
        .join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id.in_(item_ids))
    )
    tags_by_item: dict[int, list[str]] = {}
    for row in tag_result.all():
        tags_by_item.setdefault(row[1], []).append(row[0])

    # Batch-load favorites for authenticated user
    favorited_ids: set[int] = set()
    if user is not None:
        fav_result = await db.execute(
            select(Favorite.item_id).where(
                Favorite.user_id == user.id,
                Favorite.item_id.in_(item_ids),
            )
        )
        favorited_ids = {row[0] for row in fav_result.all()}

    items_out = [
        ItemSummary(
            id=item.id,
            key=item.key,
            title=item.title,
            slug=item.slug,
            library_id=item.library_id,
            dir_path=item.dir_path,
            created_at=item.created_at,
            updated_at=item.updated_at,
            default_image_path=default_imgs.get(item.id),
            creator_name=item.creator.name if item.creator else None,
            tag_names=tags_by_item.get(item.id, []),
            favorited=item.id in favorited_ids,
        )
        for item in items
    ]

    return PaginatedItems(total=total, page=page, per_page=per_page, items=items_out)


@router.get("/{key}", response_model=ItemDetail)
async def get_item(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Get item detail by key."""
    result = await db.execute(
        select(Item)
        .options(selectinload(Item.creator))
        .where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    tag_result = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = list(tag_result.scalars().all())

    file_result = await db.execute(
        select(File).where(File.item_id == item.id)
    )
    files = list(file_result.scalars().all())

    img_result = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images = list(img_result.scalars().all())

    return _build_item_detail(item, tags, files, images)


@router.patch("/{key}", response_model=ItemDetail)
async def update_item(
    key: str,
    body: ItemUpdate,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Update item metadata.  A title change triggers an atomic directory rename."""
    result = await db.execute(
        select(Item)
        .options(selectinload(Item.creator))
        .where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    # ---- Handle title rename ----
    title_changed = body.title is not None and body.title != item.title
    if title_changed:
        old_title = item.title
        new_title = body.title  # type: ignore[assignment]
        old_slug = item.slug
        new_slug = item_slug(new_title, key)
        old_dir = Path(item.dir_path)

        # Derive new dir path (same library, same shard, new slug)
        lib_result = await db.execute(
            select(Library).where(Library.id == item.library_id)
        )
        library = lib_result.scalar_one()
        new_dir = item_dir_path(library.mount_path, key, new_title)

        try:
            await atomic_rename(
                key=key,
                old_dir=old_dir,
                new_dir=new_dir,
                old_title=old_title,
                new_title=new_title,
                old_slug=old_slug,
                new_slug=new_slug,
                db=db,
            )
        except MoveError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        # Refresh item after rename (atomic_rename committed the DB update)
        result2 = await db.execute(select(Item).where(Item.key == key))
        item = result2.scalar_one()

    # ---- Apply other metadata updates ----
    needs_sidecar_refresh = title_changed
    if body.description is not None:
        item.description = body.description
        needs_sidecar_refresh = True
    if body.source_url is not None:
        item.source_url = body.source_url
        needs_sidecar_refresh = True
    if body.source_site is not None:
        item.source_site = body.source_site
        needs_sidecar_refresh = True
    if body.license is not None:
        item.license = body.license
        needs_sidecar_refresh = True

    if body.creator is not None:
        new_creator = Creator(
            name=body.creator.name,
            profile_url=body.creator.profile_url,
            source_site=body.creator.source_site,
        )
        db.add(new_creator)
        await db.flush()
        item.creator_id = new_creator.id
        item.creator = new_creator
        needs_sidecar_refresh = True

    if body.tags is not None:
        await _attach_tags(db, item, body.tags)
        needs_sidecar_refresh = True

    item.updated_at = datetime.now(UTC)
    await db.flush()

    if needs_sidecar_refresh:
        await _write_item_sidecar(db, item)

    # Load response data
    tag_result = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = list(tag_result.scalars().all())

    file_result = await db.execute(
        select(File).where(File.item_id == item.id)
    )
    files = list(file_result.scalars().all())

    img_result = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images = list(img_result.scalars().all())

    if not hasattr(item, "creator") or item.creator is None:
        creator_result = await db.execute(
            select(Creator).where(Creator.id == item.creator_id)
        ) if item.creator_id else None
        item.creator = creator_result.scalar_one_or_none() if creator_result else None

    # Update full-text search vector if any search-relevant field changed
    if needs_sidecar_refresh:
        await _update_search_vector(
            db, item.id, item.title, item.description, [t.name for t in tags]
        )

    return _build_item_detail(item, tags, files, images)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_item(
    key: str,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Move item directory to /data/trash/ and delete the DB row.

    The on-disk directory is NOT hard-deleted — it is moved to
    /data/trash/<timestamp>-<key>/ to honour "never lose data" (PRD §1).
    A future purge job (Phase 9) can prune old trash entries.
    Recorded in docs/decisions.md.
    """
    result = await db.execute(select(Item).where(Item.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    item_dir = Path(item.dir_path)

    # Move to trash (only if the dir exists)
    if item_dir.exists():
        try:
            move_to_trash(item_dir, key)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to move item directory to trash: {exc}",
            ) from exc

    # Delete DB row (cascades to files, images, item_tags)
    await db.delete(item)
    await db.flush()


@router.post("/{key}/rescan", response_model=ItemDetail)
async def rescan_item(
    key: str,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Per-item rescan (PRD §8.6): re-inventory files + resync sidecar."""
    result = await db.execute(
        select(Item)
        .options(selectinload(Item.creator))
        .where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    item_dir = Path(item.dir_path)
    sc_name = sidecar_name(item.title, key)

    # Load existing File rows for cheap-first drift check
    file_result = await db.execute(select(File).where(File.item_id == item.id))
    db_files = list(file_result.scalars().all())
    existing = {
        f.path: (f.last_seen_size, f.last_seen_mtime or f.mtime, f.sha256)
        for f in db_files
    }

    # Re-inventory
    records = inventory_item(item_dir, sc_name, existing=existing)

    to_upsert, to_delete = _apply_file_records(item, records, db_files)

    for f in to_delete:
        await db.delete(f)
    for f in to_upsert:
        db.add(f)

    item.updated_at = datetime.now(UTC)
    await db.flush()

    # Resync sidecar
    await _write_item_sidecar(db, item)

    # Load response data
    tag_result = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = list(tag_result.scalars().all())

    file_result2 = await db.execute(select(File).where(File.item_id == item.id))
    files = list(file_result2.scalars().all())

    img_result = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images = list(img_result.scalars().all())

    # Phase 4: enqueue render job if any mesh files exist (fire-and-forget)
    mesh_files = [
        f for f in files
        if f.role == FileRole.model
        and Path(f.path).suffix.lower() in MESH_EXTENSIONS
    ]
    if mesh_files:
        await _enqueue_render(item.id)

    return _build_item_detail(item, tags, files, images)


@router.patch("/{key}/default-image", response_model=ItemDetail)
async def set_default_image(
    key: str,
    body: SetDefaultImageRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Set the default image for an item (PRD §12 carousel set-default).

    The image must belong to this item.  Clears is_default on all other images
    for the item and updates Item.default_image_id.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    # Verify the requested image belongs to this item
    img_result = await db.execute(
        select(Image).where(Image.id == body.image_id, Image.item_id == item.id)
    )
    image = img_result.scalar_one_or_none()
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found or does not belong to this item.",
        )

    # Clear existing is_default flags
    await db.execute(
        sa.update(Image).where(Image.item_id == item.id).values(is_default=False)
    )
    # Set new default
    await db.execute(
        sa.update(Image).where(Image.id == body.image_id).values(is_default=True)
    )
    item.default_image_id = body.image_id
    item.updated_at = datetime.now(UTC)
    await db.flush()

    # Resync sidecar with new default
    await _write_item_sidecar(db, item)

    # Load response data
    tag_result2 = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = list(tag_result2.scalars().all())

    file_result3 = await db.execute(select(File).where(File.item_id == item.id))
    files = list(file_result3.scalars().all())

    img_result2 = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images = list(img_result2.scalars().all())

    return _build_item_detail(item, tags, files, images)
