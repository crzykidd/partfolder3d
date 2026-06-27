"""Tag browse endpoints.

GET /api/tags        → tag list with popularity counts (click-to-search)
GET /api/tags/tree  → virtual tag tree (depth from setting, default 4)

The virtual tag tree (PRD §5.2) is a pure DB/UI construct derived from the most-used
tags.  Tags with a `category` field use the namespace part (before ':') as a parent
node.  Depth N is read from the "catalog.tag_tree_depth" instance setting (default 4);
with flat tags the effective depth is 2 (namespace → tag), but the setting is honoured
for future nested categories.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_db
from ..models.setting import Setting
from ..models.tag import Tag, TagStatus

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tags", tags=["tags"])

# Setting key for the tag tree depth.
TAG_TREE_DEPTH_KEY = "catalog.tag_tree_depth"
TAG_TREE_DEPTH_DEFAULT = 4


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TagSummary(BaseModel):
    id: int
    name: str
    category: str | None
    popularity_count: int

    model_config = {"from_attributes": True}


class PaginatedTags(BaseModel):
    total: int
    page: int
    per_page: int
    tags: list[TagSummary]


class TagTreeNode(BaseModel):
    label: str
    """Display label for this node (namespace name or tag name)."""
    name: str | None
    """Canonical tag name if this is a leaf node; None for namespace nodes."""
    count: int
    """Popularity count (leaf) or sum of children (namespace)."""
    children: list[TagTreeNode] = []


TagTreeNode.model_rebuild()  # needed since children is self-referential


class TagTree(BaseModel):
    depth: int
    nodes: list[TagTreeNode]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_tag_tree_depth(db: AsyncSession) -> int:
    """Read the configured tag-tree depth from instance settings."""
    result = await db.execute(
        select(Setting).where(Setting.key == TAG_TREE_DEPTH_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return TAG_TREE_DEPTH_DEFAULT
    try:
        return int(json.loads(row.value))
    except (ValueError, TypeError):
        return TAG_TREE_DEPTH_DEFAULT


def _build_tree(tags: list[Tag], depth: int) -> list[TagTreeNode]:
    """Build the virtual tag tree from a list of Tag ORM objects.

    Strategy:
    - Tags with `category` of the form "ns" or "ns:sub" are placed under
      namespace nodes.
    - Uncategorized tags appear at the root.
    - `depth` limits how many levels of nesting to emit; with flat categories
      (single namespace) the effective depth is 2.
    - Namespace nodes aggregate their children's popularity counts.
    """
    # Group by parsed namespace path
    # e.g. category="type:keychain" → path=["type", "keychain"]
    # e.g. category="theme"        → path=["theme"]
    # e.g. category=None           → path=[]

    # We build a nested dict: ns_tree[level0][level1]... = [TagTreeNode]
    root_nodes: list[TagTreeNode] = []
    # namespace label → (sum_count, {sub_label → ...})
    ns_map: dict[str, dict] = {}

    def _ensure_ns(path: list[str]) -> dict:
        """Return the sub-dict for a namespace path, creating nodes as needed."""
        cur = ns_map
        for part in path:
            if part not in cur:
                cur[part] = {"__count": 0, "__children": {}}
            cur = cur[part]["__children"]
        return cur

    for tag in tags:
        if tag.category:
            parts = [p.strip() for p in tag.category.split(":") if p.strip()]
        else:
            parts = []

        # Limit effective depth (leaf is at depth, namespaces above it)
        # depth=1 → no namespaces, everything at root
        # depth=2 → one namespace level
        # depth=N → up to N-1 namespace levels
        effective_parts = parts[: max(0, depth - 1)]

        if not effective_parts:
            # Root-level leaf
            root_nodes.append(
                TagTreeNode(
                    label=tag.name, name=tag.name, count=tag.popularity_count
                )
            )
        else:
            # Walk / create namespace nodes
            cur = ns_map
            for depth_idx, part in enumerate(effective_parts):
                if part not in cur:
                    cur[part] = {"__count": 0, "__children": {}}
                cur[part]["__count"] += tag.popularity_count
                if depth_idx == len(effective_parts) - 1:
                    # Append leaf under this namespace
                    leaf = TagTreeNode(
                        label=tag.name, name=tag.name, count=tag.popularity_count
                    )
                    cur[part]["__children"].setdefault("__leaves", []).append(leaf)
                cur = cur[part]["__children"]

    # Convert ns_map → TagTreeNode list
    def _dict_to_nodes(d: dict) -> list[TagTreeNode]:
        nodes: list[TagTreeNode] = []
        for label, v in d.items():
            if label == "__leaves":
                nodes.extend(v)
                continue
            children = _dict_to_nodes(v.get("__children", {}))
            # Sort children by count desc
            children.sort(key=lambda n: n.count, reverse=True)
            nodes.append(
                TagTreeNode(
                    label=label,
                    name=None,
                    count=v.get("__count", 0),
                    children=children,
                )
            )
        return nodes

    ns_nodes = _dict_to_nodes(ns_map)
    # Sort namespace nodes by count desc
    ns_nodes.sort(key=lambda n: n.count, reverse=True)
    # Sort root leaf nodes by count desc
    root_nodes.sort(key=lambda n: n.count, reverse=True)

    return ns_nodes + root_nodes


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedTags)
async def list_tags(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=500),
    q: str | None = Query(default=None, description="Filter by name prefix"),
    category: str | None = Query(default=None, description="Filter by category namespace"),
    active_only: bool = Query(default=True, description="Only return active tags"),
) -> PaginatedTags:
    """List tags with popularity counts, ordered by popularity desc."""
    query = select(Tag)
    if active_only:
        query = query.where(Tag.status == TagStatus.active)
    if q:
        query = query.where(Tag.name.ilike(f"%{q}%"))
    if category:
        query = query.where(Tag.category.ilike(f"{category}%"))

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        query.order_by(Tag.popularity_count.desc(), Tag.name)
        .offset(offset)
        .limit(per_page)
    )
    tags = list(result.scalars().all())

    return PaginatedTags(
        total=total,
        page=page,
        per_page=per_page,
        tags=tags,  # type: ignore[arg-type]
    )


@router.get("/tree", response_model=TagTree)
async def get_tag_tree(
    db: Annotated[AsyncSession, Depends(get_db)],
    depth: int | None = Query(
        default=None,
        ge=1,
        le=10,
        description="Override depth (falls back to instance setting, default 4)",
    ),
) -> TagTree:
    """Return the virtual tag tree (PRD §5.2).

    Derived from most-used active tags, grouped by category namespace.
    Depth from the 'catalog.tag_tree_depth' instance setting (default 4).
    Pure DB construct — no physical directory hierarchy.
    """
    effective_depth = depth if depth is not None else await _get_tag_tree_depth(db)

    result = await db.execute(
        select(Tag)
        .where(Tag.status == TagStatus.active, Tag.popularity_count > 0)
        .order_by(Tag.popularity_count.desc(), Tag.name)
    )
    tags = list(result.scalars().all())

    nodes = _build_tree(tags, effective_depth)
    return TagTree(depth=effective_depth, nodes=nodes)
