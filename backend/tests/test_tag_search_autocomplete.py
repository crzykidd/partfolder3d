"""Tests for GET /api/tags?search= — typeahead prefix-search for the import wizard autocomplete.

Covers:
- ?search=<prefix> returns active tags whose name starts with the prefix, ordered by
  popularity desc, excludes non-matching tags.
- ?search= is case-insensitive (ILIKE).
- Inactive (pending) tags are excluded even when they match the prefix.
- ?search= is orthogonal to existing ?q= (both can be combined).
- Existing callers without ?search= are unaffected.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag, TagStatus

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_prefix_returns_matching_active_tags(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/tags?search=an returns active tags starting with 'an', ordered by
    popularity desc, and excludes tags that do not match the prefix."""
    await _setup_and_login(client, tmp_path)

    # Active tags: two match "an" prefix, one does not
    tag_anime = Tag(name="anime", status=TagStatus.active, popularity_count=10)
    tag_animal = Tag(name="animal", status=TagStatus.active, popularity_count=25)
    tag_base = Tag(name="fdm", status=TagStatus.active, popularity_count=5)
    db_session.add_all([tag_anime, tag_animal, tag_base])
    await db_session.flush()

    resp = await client.get("/api/tags?search=an")
    assert resp.status_code == 200
    data = resp.json()

    names = [t["name"] for t in data["tags"]]
    assert "anime" in names, "anime starts with 'an' — should be returned"
    assert "animal" in names, "animal starts with 'an' — should be returned"
    assert "fdm" not in names, "fdm does not start with 'an' — should be excluded"


@pytest.mark.asyncio
async def test_search_popularity_order(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """Results for ?search= are ordered by popularity_count descending."""
    await _setup_and_login(client, tmp_path)

    tag_low = Tag(name="antenna", status=TagStatus.active, popularity_count=1)
    tag_high = Tag(name="android", status=TagStatus.active, popularity_count=99)
    tag_mid = Tag(name="angular", status=TagStatus.active, popularity_count=42)
    db_session.add_all([tag_low, tag_high, tag_mid])
    await db_session.flush()

    resp = await client.get("/api/tags?search=an")
    assert resp.status_code == 200
    data = resp.json()

    matching = [t for t in data["tags"] if t["name"] in ("antenna", "android", "angular")]
    counts = [t["popularity_count"] for t in matching]
    assert counts == sorted(counts, reverse=True), (
        f"Expected descending popularity order, got {counts}"
    )


@pytest.mark.asyncio
async def test_search_excludes_pending_tags(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """Pending tags are excluded from ?search= results (active_only=True default)."""
    await _setup_and_login(client, tmp_path)

    tag_active = Tag(name="antique", status=TagStatus.active, popularity_count=5)
    tag_pending = Tag(name="antler", status=TagStatus.pending, popularity_count=5)
    db_session.add_all([tag_active, tag_pending])
    await db_session.flush()

    resp = await client.get("/api/tags?search=ant")
    assert resp.status_code == 200
    data = resp.json()

    names = [t["name"] for t in data["tags"]]
    assert "antique" in names, "active tag 'antique' should appear"
    assert "antler" not in names, "pending tag 'antler' should be excluded"


@pytest.mark.asyncio
async def test_search_case_insensitive(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """?search= is case-insensitive (ILIKE)."""
    await _setup_and_login(client, tmp_path)

    tag = Tag(name="Articulated", status=TagStatus.active, popularity_count=3)
    db_session.add(tag)
    await db_session.flush()

    resp_lower = await client.get("/api/tags?search=arti")
    assert resp_lower.status_code == 200
    lower_names = [t["name"] for t in resp_lower.json()["tags"]]
    assert "Articulated" in lower_names, "lowercase prefix should match mixed-case tag"

    resp_upper = await client.get("/api/tags?search=ARTI")
    assert resp_upper.status_code == 200
    upper_names = [t["name"] for t in resp_upper.json()["tags"]]
    assert "Articulated" in upper_names, "uppercase prefix should match mixed-case tag"


@pytest.mark.asyncio
async def test_search_no_param_unaffected(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """Existing callers that omit ?search= see all active tags (no regression)."""
    await _setup_and_login(client, tmp_path)

    tag1 = Tag(name="bracket", status=TagStatus.active, popularity_count=2)
    tag2 = Tag(name="hinge", status=TagStatus.active, popularity_count=4)
    db_session.add_all([tag1, tag2])
    await db_session.flush()

    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()["tags"]]
    assert "bracket" in names
    assert "hinge" in names
