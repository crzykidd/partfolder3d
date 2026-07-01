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

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.tag import ItemTag, Tag, TagStatus
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
    # Real usage count from COUNT(item_tags.item_id) — authoritative even if
    # popularity_count has drifted.  Added for the tag cloud (in_use filter +
    # display).  Defaults to 0 so existing callers that don't request it are safe.
    item_count: int = 0

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
    q: str | None = Query(default=None, description="Filter by name substring"),
    search: str | None = Query(
        default=None,
        description="Typeahead prefix search: filters Tag.name ILIKE '<search>%', "
        "active only, ordered by popularity. Intended for autocomplete (per_page=10 recommended).",
    ),
    category: str | None = Query(default=None, description="Filter by category namespace"),
    active_only: bool = Query(default=True, description="Only return active tags"),
    in_use_only: bool = Query(
        default=False,
        description="Only return tags that have at least one item (count > 0). "
        "Uses the real join count, not the denormalized popularity_count.",
    ),
) -> PaginatedTags:
    """List tags with real per-tag usage counts, ordered by popularity desc.

    ``item_count`` is computed from a live COUNT(item_tags.item_id) join and is
    always accurate even if ``popularity_count`` has drifted.  Pass
    ``in_use_only=true`` to get only tags that are actually in use (the tag
    cloud uses this to hide zero-item tags).
    """
    # Subquery: real per-tag item count (no duplicates thanks to PK uniqueness).
    item_count_sq = (
        select(
            ItemTag.tag_id,
            func.count(ItemTag.item_id).label("item_count"),
        )
        .group_by(ItemTag.tag_id)
        .subquery()
    )

    query = (
        select(Tag, func.coalesce(item_count_sq.c.item_count, 0).label("item_count"))
        .outerjoin(item_count_sq, Tag.id == item_count_sq.c.tag_id)
    )

    if active_only:
        query = query.where(Tag.status == TagStatus.active)
    if q:
        query = query.where(Tag.name.ilike(f"%{q}%"))
    if search:
        # Prefix match for typeahead — active_only filter still applies above.
        query = query.where(Tag.name.ilike(f"{search}%"))
    if category:
        query = query.where(Tag.category.ilike(f"{category}%"))
    if in_use_only:
        query = query.where(func.coalesce(item_count_sq.c.item_count, 0) > 0)

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    rows = await db.execute(
        query.order_by(Tag.popularity_count.desc(), Tag.name)
        .offset(offset)
        .limit(per_page)
    )

    tags = [
        TagSummary(
            id=tag.id,
            name=tag.name,
            category=tag.category,
            popularity_count=tag.popularity_count,
            item_count=item_count,
        )
        for tag, item_count in rows.all()
    ]

    return PaginatedTags(
        total=total,
        page=page,
        per_page=per_page,
        tags=tags,
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


# ---------------------------------------------------------------------------
# Starter tag seeding
# ---------------------------------------------------------------------------


class LoadDefaultsResponse(BaseModel):
    added: int
    skipped: int


@router.post("/load-defaults", response_model=LoadDefaultsResponse)
async def load_default_tags(
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoadDefaultsResponse:
    """Insert the curated starter tag set as active canonical tags (admin + CSRF).

    Idempotent: tags matched by normalized name are skipped without modification.
    Returns ``{ added, skipped }`` so the caller can surface the counts in the UI.
    """
    from ..tags_defaults import STARTER_TAGS  # noqa: PLC0415

    # Snapshot existing names for O(1) lookup (avoids N queries).
    existing_result = await db.execute(select(Tag.name))
    existing_names: set[str] = {row[0] for row in existing_result.all()}

    added = 0
    skipped = 0

    for raw_name, category in STARTER_TAGS:
        normalized = raw_name.lower().strip()
        if normalized in existing_names:
            skipped += 1
            continue
        db.add(Tag(name=normalized, category=category, status=TagStatus.active))
        existing_names.add(normalized)  # guard against duplicates within the set
        added += 1

    if added:
        await db.flush()

    return LoadDefaultsResponse(added=added, skipped=skipped)
