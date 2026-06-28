"""Tag administration endpoints (Phase 9 — PRD §13).

Admin-only operations on the tag graph.  The public tag browsing + approval
remains in routers/tags.py.  This router adds:

GET    /api/admin/tags/pending               → list pending tags
POST   /api/admin/tags/{id}/approve          → approve pending → active (idempotent)
POST   /api/admin/tags/{id}/reject           → delete a pending tag (not used for active)
PATCH  /api/admin/tags/{id}/category         → set / clear a tag's category namespace
GET    /api/admin/tags/{id}/aliases          → list aliases pointing to a tag
POST   /api/admin/tags/{id}/aliases          → add a new alias
DELETE /api/admin/tags/aliases/{alias_id}    → remove an alias
POST   /api/admin/tags/{id}/merge-into/{target_id} → merge source tag into target

Tag merge semantics (safe + idempotent):
  1. Repoint all ItemTag rows from source_id → target_id
     (ON CONFLICT DO NOTHING to handle tags already on both).
  2. Repoint all TagAlias rows from source_id → target_id.
  3. Add source.name as an alias of target (so old aliases keep resolving).
  4. Delete the source tag.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.tag import ItemTag, Tag, TagAlias, TagStatus
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/tags", tags=["admin-tags"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TagAdminOut(BaseModel):
    id: int
    name: str
    category: str | None
    popularity_count: int
    status: str

    model_config = {"from_attributes": True}


class TagAliasOut(BaseModel):
    id: int
    alias: str
    tag_id: int

    model_config = {"from_attributes": True}


class AddAliasRequest(BaseModel):
    alias: str


class SetCategoryRequest(BaseModel):
    category: str | None = None


class MergeResponse(BaseModel):
    merged: bool
    target_id: int
    source_name: str
    items_repointed: int
    aliases_repointed: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/pending", response_model=list[TagAdminOut], summary="List pending tags")
async def list_pending_tags(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TagAdminOut]:
    """Return all tags in 'pending' status awaiting admin approval."""
    result = await db.execute(
        select(Tag)
        .where(Tag.status == TagStatus.pending)
        .order_by(Tag.name)
    )
    return [TagAdminOut.model_validate(t) for t in result.scalars().all()]


@router.post(
    "/{tag_id}/approve",
    response_model=TagAdminOut,
    summary="Approve a pending tag",
)
async def approve_tag(
    tag_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagAdminOut:
    """Promote a pending tag to active status (idempotent)."""
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found.")
    if tag.status == TagStatus.active:
        return TagAdminOut.model_validate(tag)
    if tag.status != TagStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag status is '{tag.status}' — only pending tags can be approved.",
        )
    tag.status = TagStatus.active
    await db.flush()
    return TagAdminOut.model_validate(tag)


@router.post(
    "/{tag_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Reject (delete) a pending tag",
)
async def reject_tag(
    tag_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a pending tag and all its aliases.  Only pending tags can be rejected."""
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found.")
    if tag.status != TagStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending tags can be rejected. Use merge-into to retire an active tag.",
        )
    await db.delete(tag)
    await db.flush()


@router.patch(
    "/{tag_id}/category",
    response_model=TagAdminOut,
    summary="Set or clear a tag's category",
)
async def set_tag_category(
    tag_id: int,
    body: SetCategoryRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagAdminOut:
    """Set (or clear) the category namespace for a tag.

    Pass `category: null` to clear.  Category is a free-form namespace string
    (e.g. "material", "printer", "theme") used as a browse facet.
    """
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found.")
    tag.category = body.category
    await db.flush()
    return TagAdminOut.model_validate(tag)


@router.get(
    "/{tag_id}/aliases",
    response_model=list[TagAliasOut],
    summary="List aliases for a tag",
)
async def list_tag_aliases(
    tag_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TagAliasOut]:
    """Return all aliases that map onto the given canonical tag."""
    result = await db.execute(
        select(TagAlias)
        .where(TagAlias.tag_id == tag_id)
        .order_by(TagAlias.alias)
    )
    return [TagAliasOut.model_validate(a) for a in result.scalars().all()]


@router.post(
    "/{tag_id}/aliases",
    response_model=TagAliasOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an alias to a tag",
)
async def add_tag_alias(
    tag_id: int,
    body: AddAliasRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagAliasOut:
    """Add a new alias string that will resolve to the given canonical tag.

    The alias must be globally unique across all tags (enforced by DB constraint).
    """
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found.")

    # Check duplicate
    existing = await db.execute(
        select(TagAlias).where(TagAlias.alias == body.alias)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alias {body.alias!r} already exists.",
        )

    alias = TagAlias(alias=body.alias, tag_id=tag_id)
    db.add(alias)
    await db.flush()
    await db.refresh(alias)
    return TagAliasOut.model_validate(alias)


@router.delete(
    "/aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Remove an alias",
)
async def delete_tag_alias(
    alias_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove an alias mapping."""
    result = await db.execute(select(TagAlias).where(TagAlias.id == alias_id))
    alias = result.scalar_one_or_none()
    if alias is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alias not found.")
    await db.delete(alias)
    await db.flush()


@router.post(
    "/{source_id}/merge-into/{target_id}",
    response_model=MergeResponse,
    summary="Merge one tag into another",
)
async def merge_tag(
    source_id: int,
    target_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MergeResponse:
    """Merge source tag into target:

    1. Repoint ItemTag rows: source → target (skip if item already has target).
    2. Repoint TagAlias rows: source → target.
    3. Add source.name as an alias of target (preserves resolution).
    4. Delete source tag.

    Idempotent: if the alias already exists, the merge still succeeds.
    """
    if source_id == target_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot merge a tag into itself.",
        )

    src_result = await db.execute(select(Tag).where(Tag.id == source_id))
    src = src_result.scalar_one_or_none()
    if src is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source tag not found."
        )

    tgt_result = await db.execute(select(Tag).where(Tag.id == target_id))
    tgt = tgt_result.scalar_one_or_none()
    if tgt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Target tag not found."
        )

    # 1. Find items that have source but not target
    src_items_result = await db.execute(
        select(ItemTag.item_id).where(ItemTag.tag_id == source_id)
    )
    src_item_ids = {row[0] for row in src_items_result.all()}

    tgt_items_result = await db.execute(
        select(ItemTag.item_id).where(ItemTag.tag_id == target_id)
    )
    tgt_item_ids = {row[0] for row in tgt_items_result.all()}

    items_to_repoint = src_item_ids - tgt_item_ids
    items_repointed = 0

    for item_id in items_to_repoint:
        await db.execute(
            update(ItemTag)
            .where(ItemTag.item_id == item_id, ItemTag.tag_id == source_id)
            .values(tag_id=target_id)
        )
        items_repointed += 1

    # Delete remaining source ItemTag rows (items that already have target)
    await db.execute(
        delete(ItemTag).where(ItemTag.tag_id == source_id)
    )

    # 2. Repoint aliases
    aliases_result = await db.execute(
        select(TagAlias).where(TagAlias.tag_id == source_id)
    )
    aliases = list(aliases_result.scalars().all())
    aliases_repointed = 0
    for alias in aliases:
        alias.tag_id = target_id
        aliases_repointed += 1

    # 3. Add source name as alias of target (idempotent: skip if already exists)
    existing_alias = await db.execute(
        select(TagAlias).where(TagAlias.alias == src.name)
    )
    if existing_alias.scalar_one_or_none() is None:
        db.add(TagAlias(alias=src.name, tag_id=target_id))

    # Update target popularity count
    tgt.popularity_count = tgt.popularity_count + src.popularity_count

    source_name = src.name

    # 4. Delete source tag
    await db.delete(src)
    await db.flush()

    log.info(
        "merge_tag: merged %r (id=%d) into %r (id=%d); "
        "items_repointed=%d aliases_repointed=%d",
        source_name, source_id, tgt.name, target_id,
        items_repointed, aliases_repointed,
    )

    return MergeResponse(
        merged=True,
        target_id=target_id,
        source_name=source_name,
        items_repointed=items_repointed,
        aliases_repointed=aliases_repointed,
    )
