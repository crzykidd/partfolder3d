"""Creator browse endpoints.

GET /api/creators           → list creators (with item count)
GET /api/creators/{id}      → creator detail
GET /api/creators/{id}/items → items by a creator (paginated)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_db
from ..models.creator import Creator
from ..models.item import Item

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/creators", tags=["creators"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreatorDetail(BaseModel):
    id: int
    name: str
    profile_url: str | None
    source_site: str | None
    item_count: int

    model_config = {"from_attributes": False}


class CreatorItemSummary(BaseModel):
    id: int
    key: str
    title: str
    slug: str
    library_id: int
    dir_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedCreatorItems(BaseModel):
    total: int
    page: int
    per_page: int
    creator: CreatorDetail
    items: list[CreatorItemSummary]


class PaginatedCreators(BaseModel):
    total: int
    page: int
    per_page: int
    creators: list[CreatorDetail]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedCreators)
async def list_creators(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Filter by creator name"),
) -> PaginatedCreators:
    """List creators that have at least one item, ordered by item count desc."""
    query = (
        select(Creator, func.count(Item.id).label("item_count"))
        .outerjoin(Item, Item.creator_id == Creator.id)
        .group_by(Creator.id)
        .having(func.count(Item.id) > 0)
    )
    if q:
        query = query.where(Creator.name.ilike(f"%{q}%"))

    total_result = await db.execute(
        select(func.count()).select_from(
            select(Creator)
            .outerjoin(Item, Item.creator_id == Creator.id)
            .group_by(Creator.id)
            .having(func.count(Item.id) > 0)
            .subquery()
        )
    )
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        query.order_by(func.count(Item.id).desc(), Creator.name)
        .offset(offset)
        .limit(per_page)
    )

    creators = [
        CreatorDetail(
            id=row.Creator.id,
            name=row.Creator.name,
            profile_url=row.Creator.profile_url,
            source_site=row.Creator.source_site,
            item_count=row.item_count,
        )
        for row in result.all()
    ]

    return PaginatedCreators(total=total, page=page, per_page=per_page, creators=creators)


@router.get("/{creator_id}", response_model=CreatorDetail)
async def get_creator(
    creator_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreatorDetail:
    """Get creator detail with item count."""
    result = await db.execute(
        select(Creator, func.count(Item.id).label("item_count"))
        .outerjoin(Item, Item.creator_id == Creator.id)
        .where(Creator.id == creator_id)
        .group_by(Creator.id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found.")
    return CreatorDetail(
        id=row.Creator.id,
        name=row.Creator.name,
        profile_url=row.Creator.profile_url,
        source_site=row.Creator.source_site,
        item_count=row.item_count,
    )


@router.get("/{creator_id}/items", response_model=PaginatedCreatorItems)
async def list_creator_items(
    creator_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> PaginatedCreatorItems:
    """List items by a specific creator."""
    # Verify creator exists
    creator_result = await db.execute(
        select(Creator, func.count(Item.id).label("item_count"))
        .outerjoin(Item, Item.creator_id == Creator.id)
        .where(Creator.id == creator_id)
        .group_by(Creator.id)
    )
    row = creator_result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found.")

    creator_detail = CreatorDetail(
        id=row.Creator.id,
        name=row.Creator.name,
        profile_url=row.Creator.profile_url,
        source_site=row.Creator.source_site,
        item_count=row.item_count,
    )

    items_query = select(Item).where(Item.creator_id == creator_id)
    total_result = await db.execute(
        select(func.count()).select_from(items_query.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    items_result = await db.execute(
        items_query.order_by(Item.created_at.desc()).offset(offset).limit(per_page)
    )
    items = list(items_result.scalars().all())

    return PaginatedCreatorItems(
        total=total,
        page=page,
        per_page=per_page,
        creator=creator_detail,
        items=items,  # type: ignore[arg-type]
    )
