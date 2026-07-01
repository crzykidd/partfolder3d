"""Tests for tag delete (admin) and browse-by-tag in-use counts.

Covers:
- DELETE /api/admin/tags/{id} — untags items, removes aliases, returns count
- DELETE /api/admin/tags/{id} — 404 when tag not found
- GET /api/tags?in_use_only=true — returns only tags with item_count > 0
- GET /api/tags?in_use_only=true — item_count is accurate (real join count)
- GET /api/tags?in_use_only=false (default) — returns all active tags
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.library import Library
from app.models.tag import ItemTag, Tag, TagAlias, TagStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient, tmp_path: Path) -> str:
    """Initialize instance and log in as admin; return CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@test.com",
            "admin_name": "Admin",
            "admin_password": "adminpassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "adminpassword1"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


async def _make_library(db: AsyncSession, tmp_path: Path, suffix: str = "lib") -> Library:
    lib = Library(name=f"Test Library {suffix}", mount_path=str(tmp_path / suffix))
    db.add(lib)
    await db.flush()
    return lib


async def _make_item(db: AsyncSession, library_id: int, key: str, title: str) -> Item:
    item = Item(
        key=key,
        title=title,
        slug=f"{title.lower().replace(' ', '-')}-{key}",
        library_id=library_id,
        dir_path=f"/test/{key}",
    )
    db.add(item)
    await db.flush()
    return item


# ---------------------------------------------------------------------------
# Part 1 — Delete tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_tag_removes_item_tag_links(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """DELETE /api/admin/tags/{id} removes ItemTag links; items themselves remain."""
    csrf = await _setup_and_login(client, tmp_path)

    # Create library + 2 items
    lib = await _make_library(db_session, tmp_path)
    item1 = await _make_item(db_session, lib.id, "aaaaaa01", "Item One")
    item2 = await _make_item(db_session, lib.id, "aaaaaa02", "Item Two")

    # Create active tag + alias
    tag = Tag(name="delete-me", status=TagStatus.active)
    db_session.add(tag)
    await db_session.flush()

    alias = TagAlias(alias="delete-me-alias", tag_id=tag.id)
    db_session.add(alias)

    # Link both items to the tag
    db_session.add(ItemTag(item_id=item1.id, tag_id=tag.id))
    db_session.add(ItemTag(item_id=item2.id, tag_id=tag.id))
    await db_session.flush()

    tag_id = tag.id
    item1_id = item1.id
    item2_id = item2.id

    resp = await client.delete(
        f"/api/admin/tags/{tag_id}",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    assert data["items_untagged"] == 2

    # Tag itself should be gone
    tag_result = await db_session.execute(select(Tag).where(Tag.id == tag_id))
    assert tag_result.scalar_one_or_none() is None, "Tag should be deleted"

    # ItemTag links should be gone
    link_result = await db_session.execute(
        select(ItemTag).where(ItemTag.tag_id == tag_id)
    )
    assert link_result.scalars().all() == [], "ItemTag links should be removed"

    # TagAlias should be gone
    alias_result = await db_session.execute(
        select(TagAlias).where(TagAlias.tag_id == tag_id)
    )
    assert alias_result.scalars().all() == [], "TagAlias rows should be removed"

    # Items themselves must still exist
    item1_result = await db_session.execute(select(Item).where(Item.id == item1_id))
    assert item1_result.scalar_one_or_none() is not None, "Item 1 must NOT be deleted"

    item2_result = await db_session.execute(select(Item).where(Item.id == item2_id))
    assert item2_result.scalar_one_or_none() is not None, "Item 2 must NOT be deleted"


@pytest.mark.asyncio
async def test_delete_tag_no_items(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """DELETE /api/admin/tags/{id} on a tag with no items returns items_untagged=0."""
    csrf = await _setup_and_login(client, tmp_path)

    tag = Tag(name="lonely-tag", status=TagStatus.active)
    db_session.add(tag)
    await db_session.flush()
    tag_id = tag.id

    resp = await client.delete(
        f"/api/admin/tags/{tag_id}",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    assert data["items_untagged"] == 0

    tag_result = await db_session.execute(select(Tag).where(Tag.id == tag_id))
    assert tag_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_tag_pending_status(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """DELETE /api/admin/tags/{id} works for pending tags (not just active)."""
    csrf = await _setup_and_login(client, tmp_path)

    tag = Tag(name="pending-to-delete", status=TagStatus.pending)
    db_session.add(tag)
    await db_session.flush()
    tag_id = tag.id

    resp = await client.delete(
        f"/api/admin/tags/{tag_id}",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    tag_result = await db_session.execute(select(Tag).where(Tag.id == tag_id))
    assert tag_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_tag_not_found(client: AsyncClient, tmp_path: Path) -> None:
    """DELETE /api/admin/tags/{id} returns 404 when tag does not exist."""
    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.delete(
        "/api/admin/tags/99999",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Part 2 — Browse counts: in_use_only + accurate item_count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_cloud_in_use_only_filters(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/tags?in_use_only=true returns only tags with at least one item."""
    await _setup_and_login(client, tmp_path)

    lib = await _make_library(db_session, tmp_path)
    item = await _make_item(db_session, lib.id, "bbbbbb01", "Some Item")

    tag_used = Tag(name="used-tag", status=TagStatus.active)
    tag_unused = Tag(name="unused-tag", status=TagStatus.active)
    db_session.add(tag_used)
    db_session.add(tag_unused)
    await db_session.flush()

    db_session.add(ItemTag(item_id=item.id, tag_id=tag_used.id))
    await db_session.flush()

    resp = await client.get("/api/tags?in_use_only=true&active_only=true")
    assert resp.status_code == 200
    data = resp.json()

    tag_names = {t["name"] for t in data["tags"]}
    assert "used-tag" in tag_names, "used-tag should appear"
    assert "unused-tag" not in tag_names, "unused-tag should be filtered out"


@pytest.mark.asyncio
async def test_tag_cloud_accurate_item_count(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/tags returns accurate item_count from real join (not popularity_count)."""
    await _setup_and_login(client, tmp_path)

    lib = await _make_library(db_session, tmp_path)
    item1 = await _make_item(db_session, lib.id, "cccccc01", "Item C1")
    item2 = await _make_item(db_session, lib.id, "cccccc02", "Item C2")
    item3 = await _make_item(db_session, lib.id, "cccccc03", "Item C3")

    # Tag with stale popularity_count=0 but 3 real items
    tag = Tag(name="stale-count-tag", status=TagStatus.active, popularity_count=0)
    db_session.add(tag)
    await db_session.flush()

    db_session.add(ItemTag(item_id=item1.id, tag_id=tag.id))
    db_session.add(ItemTag(item_id=item2.id, tag_id=tag.id))
    db_session.add(ItemTag(item_id=item3.id, tag_id=tag.id))
    await db_session.flush()

    resp = await client.get("/api/tags?active_only=true")
    assert resp.status_code == 200
    data = resp.json()

    tag_row = next((t for t in data["tags"] if t["name"] == "stale-count-tag"), None)
    assert tag_row is not None, "stale-count-tag should appear in results"
    assert tag_row["item_count"] == 3, (
        f"item_count should be 3 (real join count), got {tag_row['item_count']}"
    )
    # popularity_count stays 0 (we didn't update it — that's the point of the test)
    assert tag_row["popularity_count"] == 0


@pytest.mark.asyncio
async def test_tag_in_use_only_false_returns_all(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/tags?in_use_only=false (default) returns all active tags."""
    await _setup_and_login(client, tmp_path)

    tag_used = Tag(name="with-items-tag", status=TagStatus.active)
    tag_empty = Tag(name="no-items-tag", status=TagStatus.active)
    db_session.add(tag_used)
    db_session.add(tag_empty)
    await db_session.flush()

    lib = await _make_library(db_session, tmp_path, suffix="lib2")
    item = await _make_item(db_session, lib.id, "dddddd01", "Item D")
    db_session.add(ItemTag(item_id=item.id, tag_id=tag_used.id))
    await db_session.flush()

    resp = await client.get("/api/tags?active_only=true")
    assert resp.status_code == 200
    data = resp.json()

    tag_names = {t["name"] for t in data["tags"]}
    assert "with-items-tag" in tag_names
    assert "no-items-tag" in tag_names, "in_use_only defaults to false → all tags returned"


# ---------------------------------------------------------------------------
# Part 3 — Admin pending list: item_count is accurate (real join count)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_pending_list_item_count(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/admin/tags/pending returns accurate item_count from real join.

    A pending tag applied to N items reports item_count==N; an unused pending
    tag reports item_count==0 (popularity_count stays 0 throughout).
    """
    await _setup_and_login(client, tmp_path)

    lib = await _make_library(db_session, tmp_path, suffix="pending-counts")
    item1 = await _make_item(db_session, lib.id, "eeeeee01", "Item E1")
    item2 = await _make_item(db_session, lib.id, "eeeeee02", "Item E2")

    # Two pending tags; one used, one unused
    tag_used = Tag(name="pending-used-tag", status=TagStatus.pending, popularity_count=0)
    tag_empty = Tag(name="pending-empty-tag", status=TagStatus.pending, popularity_count=0)
    db_session.add(tag_used)
    db_session.add(tag_empty)
    await db_session.flush()

    # Link 2 items to the used tag; leave empty tag unlinked
    db_session.add(ItemTag(item_id=item1.id, tag_id=tag_used.id))
    db_session.add(ItemTag(item_id=item2.id, tag_id=tag_used.id))
    await db_session.flush()

    resp = await client.get("/api/admin/tags/pending")
    assert resp.status_code == 200
    rows = resp.json()

    used_row = next((t for t in rows if t["name"] == "pending-used-tag"), None)
    empty_row = next((t for t in rows if t["name"] == "pending-empty-tag"), None)

    assert used_row is not None, "pending-used-tag should appear in pending list"
    assert used_row["item_count"] == 2, (
        f"item_count should be 2 (real join count), got {used_row['item_count']}"
    )
    assert used_row["popularity_count"] == 0, "popularity_count is never maintained"

    assert empty_row is not None, "pending-empty-tag should appear in pending list"
    assert empty_row["item_count"] == 0, (
        f"unused pending tag should have item_count==0, got {empty_row['item_count']}"
    )
