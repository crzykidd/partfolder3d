"""Tests for library hard-delete (purge) and re-enable endpoints (issue #11)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> str:
    """Initialize instance and log in as admin; returns CSRF token."""
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


async def _create_library(
    client: AsyncClient,
    csrf: str,
    name: str = "Test Library",
    mount_path: str = "/tmp/testlib",
) -> int:
    resp = await client.post(
        "/api/libraries",
        json={"name": name, "mount_path": mount_path},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _find_lib(libs: list[dict], lib_id: int) -> dict:
    return next(entry for entry in libs if entry["id"] == lib_id)


# ---------------------------------------------------------------------------
# Purge (hard-delete) — empty library
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_empty_library_succeeds(
    client: AsyncClient, tmp_path: Path
) -> None:
    """DELETE /api/libraries/{id}/purge on an empty library returns 204."""
    csrf = await _setup_and_login(client)
    lib_id = await _create_library(client, csrf)

    # Soft-disable first (purge works on disabled or enabled)
    resp = await client.delete(f"/api/libraries/{lib_id}", headers={"x-csrf-token": csrf})
    assert resp.status_code == 204

    # Purge the empty library
    resp = await client.delete(f"/api/libraries/{lib_id}/purge", headers={"x-csrf-token": csrf})
    assert resp.status_code == 204

    # Library should no longer appear in the list
    list_resp = await client.get("/api/libraries")
    assert list_resp.status_code == 200
    ids = [lib["id"] for lib in list_resp.json()]
    assert lib_id not in ids


# ---------------------------------------------------------------------------
# Purge — non-empty library rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_nonempty_library_rejected(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """DELETE /api/libraries/{id}/purge on a library with items returns 409."""
    csrf = await _setup_and_login(client)
    lib_id = await _create_library(client, csrf, mount_path="/tmp/testlib2")

    # Insert an item directly into the DB to simulate a non-empty library.
    item = Item(
        key="testkey1",
        title="A Test Item",
        slug="a-test-item-testkey1",
        library_id=lib_id,
        dir_path="/tmp/testlib2/a-test-item-testkey1",
    )
    db_session.add(item)
    await db_session.flush()

    resp = await client.delete(f"/api/libraries/{lib_id}/purge", headers={"x-csrf-token": csrf})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "1 asset" in detail
    assert "#25" in detail


# ---------------------------------------------------------------------------
# Re-enable a disabled library
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_library_works(
    client: AsyncClient, tmp_path: Path
) -> None:
    """POST /api/libraries/{id}/enable re-enables a disabled library."""
    csrf = await _setup_and_login(client)
    lib_id = await _create_library(client, csrf, mount_path="/tmp/testlib3")

    # Disable it
    resp = await client.delete(f"/api/libraries/{lib_id}", headers={"x-csrf-token": csrf})
    assert resp.status_code == 204

    # Verify disabled in list
    list_resp = await client.get("/api/libraries")
    lib = _find_lib(list_resp.json(), lib_id)
    assert lib["enabled"] is False

    # Re-enable
    resp = await client.post(f"/api/libraries/{lib_id}/enable", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["id"] == lib_id
    assert data["item_count"] == 0

    # Verify enabled in list
    list_resp2 = await client.get("/api/libraries")
    lib2 = _find_lib(list_resp2.json(), lib_id)
    assert lib2["enabled"] is True


# ---------------------------------------------------------------------------
# item_count in list response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_libraries_includes_item_count(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/libraries returns item_count for each library."""
    csrf = await _setup_and_login(client)
    lib_id = await _create_library(client, csrf, mount_path="/tmp/testlib4")

    # No items yet
    list_resp = await client.get("/api/libraries")
    lib = _find_lib(list_resp.json(), lib_id)
    assert lib["item_count"] == 0

    # Add an item
    item = Item(
        key="testkey2",
        title="Another Item",
        slug="another-item-testkey2",
        library_id=lib_id,
        dir_path="/tmp/testlib4/another-item-testkey2",
    )
    db_session.add(item)
    await db_session.flush()

    list_resp2 = await client.get("/api/libraries")
    lib2 = _find_lib(list_resp2.json(), lib_id)
    assert lib2["item_count"] == 1
