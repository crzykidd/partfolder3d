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
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import sqlalchemy as sa
from arq.connections import ArqRedis
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi import (
    File as FastAPIFile,
)
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.deps import csrf_protect, get_current_user, get_db, get_optional_user
from ..models.creator import Creator
from ..models.favorite import Favorite
from ..models.file import File
from ..models.image import Image, ImageSource
from ..models.item import Item
from ..models.job import Job
from ..models.library import Library
from ..models.tag import ItemTag, Tag
from ..models.user import User
from ..services.item_helpers import (
    _attach_tags,
    _enqueue_analyze,
    _enqueue_render,
    _update_search_vector,
    _write_item_sidecar,
)
from ..storage.inventory import FileRecord, hash_file_sha256, infer_role, inventory_item
from ..storage.journal import MoveError, atomic_rename, move_to_trash
from ..storage.keys import generate_unique_key
from ..storage.link_url import validate_link_url
from ..storage.paths import item_dir_path, item_slug, sidecar_name
from ..worker.arq_pool import get_arq_pool

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["items"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreatorIn(BaseModel):
    name: str
    profile_url: str | None = None
    source_site: str | None = None

    _validate_profile_url = field_validator("profile_url")(validate_link_url)


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

    _validate_source_url = field_validator("source_url")(validate_link_url)


class ItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    license: str | None = None
    creator: CreatorIn | None = None
    tags: list[str] | None = None

    _validate_source_url = field_validator("source_url")(validate_link_url)


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
    # Phase 16: per-object mesh analysis (null until worker runs)
    object_analysis: Any | None = None
    # render-rework-A: true when the file can be previewed in the browser 3D viewer.
    # Gated by extension (.stl/.obj/.3mf) and file size ≤ BROWSER_PREVIEW_MAX_MB.
    preview_3d: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _compute_preview_3d(self) -> FileOut:
        from app.config import settings  # noqa: PLC0415

        _PREVIEW_EXTS = frozenset({".stl", ".obj", ".3mf"})
        ext = Path(self.path).suffix.lower()
        max_bytes = settings.BROWSER_PREVIEW_MAX_MB * 1024 * 1024
        self.preview_3d = ext in _PREVIEW_EXTS and self.size <= max_bytes
        return self


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
    # Phase 15: local-modification tracking
    is_modified: bool = False           # effective state (override wins over auto)
    locally_modified_at: datetime | None = None
    modified_override: str | None = None
    # Phase 16: object-analysis aggregate (null until at least one file is analyzed)
    analysis_total_objects: int | None = None
    analysis_total_colors: int | None = None
    analysis_total_est_grams: float | None = None

    model_config = {"from_attributes": True}


class PatchModifiedOverrideRequest(BaseModel):
    override: str | None = None  # 'modified' | 'original' | null


class ItemJobOut(BaseModel):
    """Slim job record surfaced on the item detail page (active + recent failed)."""
    id: str
    type: str
    status: str
    progress: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": False}


class PaginatedItems(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[ItemSummary]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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


def _effective_is_modified(item: Item) -> bool:
    """Compute the effective is_modified flag.

    override='modified' → True
    override='original' → False
    override=None       → locally_modified (auto)
    """
    override = getattr(item, "modified_override", None)
    if override == "modified":
        return True
    if override == "original":
        return False
    return bool(getattr(item, "locally_modified", False))


def _build_analysis_aggregate(
    files: list[File],
) -> tuple[int | None, int | None, float | None]:
    """Compute item-level analysis aggregate from analyzed file rows.

    Returns (total_objects, total_colors, total_est_grams).
    Returns (None, None, None) if no files have been analyzed yet.
    """
    total_objects = 0
    total_colors = 0
    total_grams = 0.0
    any_analyzed = False

    for f in files:
        a = getattr(f, "object_analysis", None)
        if not isinstance(a, dict):
            continue
        any_analyzed = True
        total_objects += a.get("total_objects", 0)
        total_colors += a.get("total_colors", 0)
        g = a.get("total_est_grams")
        if g is not None:
            total_grams += float(g)

    if not any_analyzed:
        return None, None, None
    return total_objects, total_colors, round(total_grams, 3)


def _build_item_detail(
    item: Item,
    tags: list[Tag],
    files: list[File],
    images: list[Image],
) -> dict[str, Any]:
    """Build the ItemDetail dict from loaded ORM objects."""
    total_obj, total_col, total_g = _build_analysis_aggregate(files)
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
        # Phase 15: local-modification tracking
        "is_modified": _effective_is_modified(item),
        "locally_modified_at": getattr(item, "locally_modified_at", None),
        "modified_override": getattr(item, "modified_override", None),
        # Phase 16: object-analysis aggregate
        "analysis_total_objects": total_obj,
        "analysis_total_colors": total_col,
        "analysis_total_est_grams": total_g,
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
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
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
    await _enqueue_render(item.id, pool=arq)
    # Phase 16: enqueue mesh analysis alongside render
    await _enqueue_analyze(item.id, pool=arq)

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
            log.warning("update_item: rename failed for item %s: %s", key, exc)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Failed to rename item directory.",
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
    The daily orphan_cleanup cron prunes trash entries older than
    TRASH_RETENTION_DAYS (default 30d).
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
            log.exception("delete_item: failed to move item %s directory to trash", key)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to move item directory to trash.",
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
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> dict[str, Any]:
    """Per-item rescan (PRD §8.6): re-inventory + sidecar resync via the reconcile engine.

    Drives the same engine as the scheduled library scan so the per-item Rescan button
    produces identical Issues / ChangeLog / ReviewItem outcomes.
    """
    from ..worker.reconcile import load_mode_settings, reconcile_one_item  # noqa: PLC0415

    result = await db.execute(
        select(Item)
        .options(selectinload(Item.creator))
        .where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    # Per-item user-triggered rescan uses "auto" for file_changes and sidecar_sync
    # so changes apply immediately; the nightly library scan uses the (more
    # conservative) DB-stored defaults.
    mode_settings = await load_mode_settings(db)
    mode_settings = {**mode_settings, "file_changes": "auto", "sidecar_sync": "auto"}
    await reconcile_one_item(
        db,
        item,
        mode_settings=mode_settings,
        url_validator=None,  # URL validation requires explicit opt-in
        source="per_item_rescan",
    )

    # Load updated response data
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

    # Reload creator (may have changed)
    if item.creator_id and not item.creator:
        from ..models.creator import Creator  # noqa: PLC0415
        creator_result = await db.execute(select(Creator).where(Creator.id == item.creator_id))
        item.creator = creator_result.scalar_one_or_none()

    # Phase 16: re-enqueue analysis on rescan (fire-and-forget)
    await _enqueue_analyze(item.id, pool=arq)

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


@router.patch("/{key}/modified-override", response_model=ItemDetail)
async def patch_modified_override(
    key: str,
    body: PatchModifiedOverrideRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Set or clear the manual modified-override for an item (Phase 15).

    Body: { "override": "modified" | "original" | null }
      "modified"  — permanently mark as modified (even if files match baseline)
      "original"  — permanently mark as original (even if files diverge)
      null        — return to auto mode (let the scan engine decide)

    Requires authentication + CSRF.  Does not require source_url to be set, but
    the flag is only meaningful (and surfaced in UI) when source_url is present.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    override = body.override
    if override is not None and override not in ("modified", "original"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="override must be 'modified', 'original', or null.",
        )

    item.modified_override = override
    item.updated_at = datetime.now(UTC)
    await db.flush()

    # Write sidecar so the modified_state block reflects the new effective state
    await _write_item_sidecar(db, item)

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

    return _build_item_detail(item, tags, files, images)


@router.get("/{key}/jobs", response_model=list[ItemJobOut])
async def list_item_jobs(
    key: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ItemJobOut]:
    """Return active (queued/running) + recent non-archived failed jobs for an item.

    Used by the Object Breakdown section to show per-file analysis status
    (running progress %, queued, or failure error) instead of a generic
    "Analysis pending" message.

    Decision: "recent failed" = non-archived failed rows (no time cap).  A failed
    job stays relevant until the user archives it or until a retry/rescan
    produces a new succeeded row (which supersedes and auto-archives the old one).
    Archived jobs are excluded.
    """
    # Resolve item
    result = await db.execute(select(Item).where(Item.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    job_result = await db.execute(
        select(Job)
        .where(
            Job.item_id == item.id,
            Job.archived_at.is_(None),
            sa.or_(
                Job.status.in_(["queued", "running"]),
                Job.status == "failed",
            ),
        )
        .order_by(Job.created_at.desc())
    )
    jobs = list(job_result.scalars().all())
    return [
        ItemJobOut(
            id=str(j.id),
            type=j.type,
            status=j.status,
            progress=j.progress,
            error=j.error,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
        )
        for j in jobs
    ]


# ---------------------------------------------------------------------------
# Allowed image MIME types / extensions for upload
# ---------------------------------------------------------------------------

_ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@router.post("/{key}/images", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    key: str,
    file: Annotated[UploadFile, FastAPIFile(...)],
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source: Annotated[str, Query()] = "uploaded",
) -> ImageOut:
    """Upload an image to an existing item.

    Accepts png/jpg/jpeg/webp/gif.  Writes the file into the item's
    ``images/`` subdirectory with a safe unique name and creates an Image row.
    ``source`` query param accepts ``uploaded`` (default) or ``captured``
    (browser 3D viewer screenshot).  Syncs the sidecar.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    # Validate content-type / extension
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    suffix = Path(file.filename or "").suffix.lower()
    if content_type not in _ALLOWED_IMAGE_TYPES and suffix not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported image type.  Allowed: png, jpg, jpeg, webp, gif.",
        )

    # Derive a safe extension (prefer from extension; fall back to content-type)
    if suffix in _ALLOWED_IMAGE_EXTS:
        safe_ext = suffix
    else:
        ct_to_ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        safe_ext = ct_to_ext.get(content_type, ".jpg")

    # Generate a unique filename to avoid collisions / path traversal
    unique_stem = secrets.token_hex(8)
    file_prefix = "capture" if source == "captured" else "upload"
    safe_filename = f"{file_prefix}_{unique_stem}{safe_ext}"

    # Write into item_dir/images/
    item_dir = Path(item.dir_path)
    images_dir = item_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / safe_filename
    rel_path = str(dest.relative_to(item_dir))

    # Path traversal guard (should be impossible with safe_filename but be defensive)
    try:
        dest.resolve().relative_to(item_dir.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
        ) from exc

    data = await file.read()
    dest.write_bytes(data)

    # Validate and resolve the source value
    _source = ImageSource.uploaded
    if source == "captured":
        _source = ImageSource.captured

    # Determine order (after all existing images)
    order_result = await db.execute(
        sa.select(sa.func.max(Image.order)).where(Image.item_id == item.id)
    )
    max_order = order_result.scalar_one_or_none()
    new_order = (max_order or 0) + 1

    img = Image(
        item_id=item.id,
        path=rel_path,
        source=_source,
        is_default=False,
        order=new_order,
    )
    db.add(img)
    await db.flush()
    await db.refresh(img)

    item.updated_at = datetime.now(UTC)
    await db.flush()

    await _write_item_sidecar(db, item)

    return ImageOut(
        id=img.id,
        path=img.path,
        source=img.source.value,
        is_default=img.is_default,
        order=img.order,
    )


@router.delete(
    "/{key}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_image(
    key: str,
    image_id: int,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete an image from an item.

    Removes the DB row and (if it exists) the file from the item dir.
    If the deleted image was the default, reassigns default to the first
    remaining image (or leaves none if no images remain).  Syncs the sidecar.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    img_result = await db.execute(
        select(Image).where(Image.id == image_id, Image.item_id == item.id)
    )
    image = img_result.scalar_one_or_none()
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found or does not belong to this item.",
        )

    was_default = image.is_default

    # Remove the on-disk file (best-effort — don't fail if missing)
    try:
        file_path = Path(item.dir_path) / image.path
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except OSError as exc:
        log.warning("delete_image: could not remove file %s: %s", image.path, exc)

    await db.delete(image)
    await db.flush()

    # Reassign default if needed
    if was_default:
        remaining_result = await db.execute(
            select(Image).where(Image.item_id == item.id).order_by(Image.order).limit(1)
        )
        first_remaining = remaining_result.scalar_one_or_none()
        if first_remaining is not None:
            await db.execute(
                sa.update(Image).where(Image.item_id == item.id).values(is_default=False)
            )
            await db.execute(
                sa.update(Image).where(Image.id == first_remaining.id).values(is_default=True)
            )
            item.default_image_id = first_remaining.id
        else:
            item.default_image_id = None

    item.updated_at = datetime.now(UTC)
    await db.flush()

    await _write_item_sidecar(db, item)


# ---------------------------------------------------------------------------
# File management: upload, delete, rename (issues #18 / #19)
# ---------------------------------------------------------------------------

_ALLOWED_FILE_EXTENSIONS = frozenset({
    # 3D model formats
    ".stl", ".3mf", ".obj", ".ply", ".blend", ".f3d",
    ".step", ".stp", ".fcstd", ".amf", ".dae",
    # Archive
    ".zip",
    # G-code
    ".gcode", ".gco", ".bgcode",
    # Documents / project notes
    ".pdf", ".txt", ".md",
})


class RenameFileRequest(BaseModel):
    name: str  # new basename only — no path separators


@router.post(
    "/{key}/files",
    response_model=FileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    key: str,
    file: Annotated[UploadFile, FastAPIFile(...)],
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> FileOut:
    """Upload an additional file to an existing item.

    Accepts model formats, archives, and g-code.  Saves the file into the item
    directory root with a sanitized, collision-safe filename.  Creates a File row,
    syncs the sidecar, and enqueues analyze + render (3MF skips render via the
    model_extensions guard in _enqueue_render).
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported file type {suffix!r}. "
                f"Allowed: {', '.join(sorted(_ALLOWED_FILE_EXTENSIONS))}"
            ),
        )

    # Derive a safe filename from the uploaded name.
    original_stem = Path(file.filename or "upload").stem
    safe_stem = re.sub(r"[^\w.\-]", "_", original_stem)[:200] or "upload"
    safe_filename = f"{safe_stem}{suffix}"

    item_dir = Path(item.dir_path)
    dest = item_dir / safe_filename
    counter = 1
    while dest.exists():
        dest = item_dir / f"{safe_stem}_{counter}{suffix}"
        counter += 1

    rel_path = str(dest.relative_to(item_dir))

    # Path traversal guard (belt-and-suspenders after safe_stem construction).
    try:
        dest.resolve().relative_to(item_dir.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path."
        ) from exc

    data = await file.read()
    dest.write_bytes(data)

    stat = dest.stat()
    sha256 = hash_file_sha256(dest)
    role = infer_role(rel_path)
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    size = stat.st_size

    f = File(
        item_id=item.id,
        path=rel_path,
        role=role,
        size=size,
        sha256=sha256,
        mtime=mtime,
        last_seen_size=size,
        last_seen_mtime=mtime,
    )
    db.add(f)
    await db.flush()
    await db.refresh(f)

    item.updated_at = datetime.now(UTC)
    await db.flush()

    await _write_item_sidecar(db, item)

    await _enqueue_analyze(item.id, pool=arq)
    await _enqueue_render(item.id, pool=arq, model_extensions=[suffix])

    return FileOut(
        id=f.id,
        path=f.path,
        role=f.role.value,
        size=f.size,
        sha256=f.sha256,
        object_analysis=None,
    )


@router.delete(
    "/{key}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_file(
    key: str,
    file_id: int,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a single file from an item.

    Removes the DB row and (if it exists on disk) the physical file.
    Syncs the sidecar.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    file_result = await db.execute(
        select(File).where(File.id == file_id, File.item_id == item.id)
    )
    f = file_result.scalar_one_or_none()
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or does not belong to this item.",
        )

    # Remove the on-disk file (best-effort — don't fail if already missing).
    try:
        file_path = Path(item.dir_path) / f.path
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except OSError as exc:
        log.warning("delete_file: could not remove file %s: %s", f.path, exc)

    await db.delete(f)
    item.updated_at = datetime.now(UTC)
    await db.flush()

    await _write_item_sidecar(db, item)


@router.patch(
    "/{key}/files/{file_id}",
    response_model=FileOut,
)
async def rename_file(
    key: str,
    file_id: int,
    body: RenameFileRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileOut:
    """Rename a file (new basename only — file stays in its current directory).

    Updates the on-disk file and the files.path DB column.  Re-infers role from
    the new extension.  Syncs the sidecar.  The new name must be a plain filename
    with no path separators or traversal components.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    file_result = await db.execute(
        select(File).where(File.id == file_id, File.item_id == item.id)
    )
    f = file_result.scalar_one_or_none()
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or does not belong to this item.",
        )

    new_name = body.name.strip()

    if not new_name or "/" in new_name or "\\" in new_name or ".." in new_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid filename: must be a plain name with no path separators.",
        )
    if len(new_name) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filename too long (max 255 characters).",
        )

    item_dir = Path(item.dir_path)
    old_abs = item_dir / f.path

    # New path: same parent directory as the current file.
    parent = Path(f.path).parent
    new_rel = str(parent / new_name)
    new_abs = item_dir / new_rel

    # Path traversal guard.
    try:
        new_abs.resolve().relative_to(item_dir.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
        ) from exc

    # Collision guard.
    if new_abs.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A file named {new_name!r} already exists in this location.",
        )

    # Rename on disk (atomic on same filesystem).
    if old_abs.exists():
        try:
            old_abs.rename(new_abs)
        except OSError as exc:
            log.exception("rename_file: failed to rename %s on disk", f.path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to rename file on disk.",
            ) from exc
    else:
        log.warning(
            "rename_file: source %s not found on disk — updating DB path only", f.path
        )

    f.path = new_rel
    f.role = infer_role(new_rel)
    item.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(f)

    await _write_item_sidecar(db, item)

    return FileOut(
        id=f.id,
        path=f.path,
        role=f.role.value,
        size=f.size,
        sha256=f.sha256,
        object_analysis=f.object_analysis,
    )


