"""Shared helpers for the items router package.

Split out of the former monolithic ``routers/items.py`` (audit §D). Pure code
movement — no behavior change.

``_effective_is_modified`` is re-exported from the package ``__init__`` because
``routers/shares.py`` and ``tests/test_phase15_local_modified.py`` import it as
``from app.routers.items import _effective_is_modified``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import func

from ...models.file import File
from ...models.image import Image
from ...models.item import Item
from ...models.tag import Tag
from ...storage.inventory import FileRecord


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
