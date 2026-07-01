"""JSON catalog export endpoint (Phase 9 — PRD §13).

GET /api/admin/export/catalog → stream full catalog as JSON.

Exports: items (with tags, creator, files, images, print records).
Does NOT export binary files — only structured metadata.
Admin-only.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.deps import get_db, require_admin
from ..models.creator import Creator
from ..models.item import Item
from ..models.tag import Tag, TagAlias
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/export", tags=["admin-export"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ser(v: object) -> object:
    """JSON-serialize datetime/date to ISO strings."""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/catalog",
    summary="Export full catalog as JSON",
    response_class=StreamingResponse,
)
async def export_catalog(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Stream the entire catalog (items, tags, creators) as a JSON document.

    The response is a streaming JSON object with the structure:
      {
        "exported_at": "<ISO timestamp>",
        "items": [...],
        "tags": [...],
        "creators": [...],
        "tag_aliases": [...]
      }

    Binary files are not included — only structured metadata.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    from ..models.print_record import PrintRecord  # noqa: PLC0415
    from ..models.tag import ItemTag  # noqa: PLC0415

    exported_at = datetime.now(UTC).isoformat()

    # Load all data upfront (catalog export is infrequent; for very large catalogs
    # a true streaming approach would paginate, but that adds significant complexity
    # for a rarely-used admin endpoint).

    items_result = await db.execute(
        select(Item)
        .options(
            selectinload(Item.item_tags).selectinload(ItemTag.tag),  # type: ignore[attr-defined]
            selectinload(Item.files),  # type: ignore[attr-defined]
            selectinload(Item.images),  # type: ignore[attr-defined]
            selectinload(Item.creator),  # type: ignore[attr-defined]
        )
        .order_by(Item.id)
    )
    items = list(items_result.scalars().all())

    tags_result = await db.execute(select(Tag).order_by(Tag.id))
    tags = list(tags_result.scalars().all())

    aliases_result = await db.execute(select(TagAlias).order_by(TagAlias.id))
    aliases = list(aliases_result.scalars().all())

    creators_result = await db.execute(select(Creator).order_by(Creator.id))
    creators = list(creators_result.scalars().all())

    # Load print records
    pr_result = await db.execute(select(PrintRecord).order_by(PrintRecord.id))
    print_records = list(pr_result.scalars().all())

    def _item_to_dict(item: Item) -> dict:
        return {
            "id": item.id,
            "key": item.key,
            "title": item.title,
            "slug": item.slug,
            "description": item.description,
            "source_url": item.source_url,
            "source_site": item.source_site,
            "license": item.license,
            "creator_id": item.creator_id,
            "library_id": item.library_id,
            "dir_path": item.dir_path,
            "created_at": _ser(item.created_at),
            "updated_at": _ser(item.updated_at),
            "tags": [it.tag.name for it in item.item_tags],
            "files": [
                {
                    "id": f.id,
                    "path": f.path,
                    "role": f.role.value if hasattr(f.role, "value") else f.role,
                    "size": f.size,
                    "sha256": f.sha256,
                }
                for f in item.files
            ],
            "images": [
                {
                    "id": img.id,
                    "path": img.path,
                    "source": img.source.value if hasattr(img.source, "value") else img.source,
                    "is_default": img.is_default,
                    "order": img.order,
                }
                for img in item.images
            ],
        }

    def _tag_to_dict(tag: Tag) -> dict:
        return {
            "id": tag.id,
            "name": tag.name,
            "category": tag.category,
            "popularity_count": tag.popularity_count,
            "status": tag.status.value if hasattr(tag.status, "value") else tag.status,
            "created_at": _ser(tag.created_at),
        }

    def _alias_to_dict(alias: TagAlias) -> dict:
        return {"id": alias.id, "alias": alias.alias, "tag_id": alias.tag_id}

    def _creator_to_dict(c: Creator) -> dict:
        return {
            "id": c.id,
            "name": c.name,
            "profile_url": c.profile_url,
            "source_site": c.source_site,
        }

    def _pr_to_dict(pr: PrintRecord) -> dict:
        return {
            "id": pr.id,
            "item_id": pr.item_id,
            "note": pr.note,
            "visibility": pr.visibility,
            "date": _ser(pr.date),
            "printer": pr.printer,
            "material": pr.material,
            "success": pr.success,
            "rating": pr.rating,
            "created_at": _ser(pr.created_at),
        }

    data = {
        "exported_at": exported_at,
        "items": [_item_to_dict(i) for i in items],
        "tags": [_tag_to_dict(t) for t in tags],
        "tag_aliases": [_alias_to_dict(a) for a in aliases],
        "creators": [_creator_to_dict(c) for c in creators],
        "print_records": [_pr_to_dict(pr) for pr in print_records],
    }

    json_bytes = json.dumps(data, indent=2, default=str).encode()

    async def stream_json() -> AsyncGenerator[bytes, None]:
        yield json_bytes

    return StreamingResponse(
        stream_json(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="catalog_{exported_at[:10]}.json"'
        },
    )
