"""Tests for the catalog has_asset flag and filter.

Covers:
- has_asset=True when item has a model file (role='model')
- has_asset=True when item has a gcode file (role='gcode')
- has_asset=False when item has only image/render/other files
- has_asset=False when item has no files at all
- GET /api/items?has_asset=true returns only items with model/gcode files
- GET /api/items?has_asset=false returns only items without model/gcode files
- has_asset filter composes correctly with the library filter
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File, FileRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _login_admin(client: AsyncClient, tmp_path: Path) -> str:
    """Setup instance + login as admin; return CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@test.com",
            "admin_name": "Admin",
            "admin_password": "adminpassword1",
        },
    )
    await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "adminpassword1"},
    )
    return client.cookies.get("pf3d_csrf", "")


async def _create_lib(client: AsyncClient, tmp_path: Path, csrf: str, suffix: str) -> int:
    """Create a library; return its id."""
    mount = str(tmp_path / suffix)
    Path(mount).mkdir(parents=True, exist_ok=True)
    resp = await client.post(
        "/api/libraries",
        json={"name": f"Lib-{suffix}", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_item(
    client: AsyncClient,
    csrf: str,
    title: str,
    library_id: int,
) -> dict:
    """Create an item; return the response dict."""
    resp = await client.post(
        "/api/items",
        json={"title": title, "library_id": library_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _attach_file(
    db: AsyncSession,
    item_id: int,
    path: str,
    role: FileRole,
) -> None:
    """Directly insert a File row into the DB (bypasses real filesystem)."""
    from datetime import UTC, datetime  # noqa: PLC0415

    f = File(
        item_id=item_id,
        path=path,
        role=role,
        size=1024,
        sha256=None,
        mtime=datetime.now(UTC),
        last_seen_size=1024,
        last_seen_mtime=datetime.now(UTC),
    )
    db.add(f)
    await db.flush()


# ---------------------------------------------------------------------------
# has_asset flag in the catalog list response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_asset_true_for_model_file(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """has_asset=True when item has a file with role='model'."""
    csrf = await _login_admin(client, tmp_path)
    lib_id = await _create_lib(client, tmp_path, csrf, "lib_model")
    item = await _create_item(client, csrf, "Dragon STL", lib_id)

    # Insert a model-role file directly via the test session.
    await _attach_file(db_session, item["id"], "dragon.stl", FileRole.model)
    db_session.expire_all()

    resp = await client.get("/api/items", params={"library_ids": lib_id})
    assert resp.status_code == 200
    items = resp.json()["items"]
    target = next((i for i in items if i["key"] == item["key"]), None)
    assert target is not None
    assert target["has_asset"] is True


@pytest.mark.asyncio
async def test_has_asset_true_for_gcode_file(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """has_asset=True when item has a file with role='gcode'."""
    csrf = await _login_admin(client, tmp_path)
    lib_id = await _create_lib(client, tmp_path, csrf, "lib_gcode")
    item = await _create_item(client, csrf, "Print Plate", lib_id)

    await _attach_file(db_session, item["id"], "prints/plate.gcode", FileRole.gcode)
    db_session.expire_all()

    resp = await client.get("/api/items", params={"library_ids": lib_id})
    assert resp.status_code == 200
    items = resp.json()["items"]
    target = next((i for i in items if i["key"] == item["key"]), None)
    assert target is not None
    assert target["has_asset"] is True


@pytest.mark.asyncio
async def test_has_asset_false_for_images_only(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """has_asset=False when item has only image/render files (no model or gcode)."""
    csrf = await _login_admin(client, tmp_path)
    lib_id = await _create_lib(client, tmp_path, csrf, "lib_imgonly")
    item = await _create_item(client, csrf, "URL Import (images only)", lib_id)

    await _attach_file(db_session, item["id"], "images/cover.jpg", FileRole.image)
    await _attach_file(db_session, item["id"], "renders/thumb.png", FileRole.render)
    db_session.expire_all()

    resp = await client.get("/api/items", params={"library_ids": lib_id})
    assert resp.status_code == 200
    items = resp.json()["items"]
    target = next((i for i in items if i["key"] == item["key"]), None)
    assert target is not None
    assert target["has_asset"] is False


@pytest.mark.asyncio
async def test_has_asset_false_for_zero_files(
    client: AsyncClient, tmp_path: Path
) -> None:
    """has_asset=False when item has no files at all (metadata-only)."""
    csrf = await _login_admin(client, tmp_path)
    lib_id = await _create_lib(client, tmp_path, csrf, "lib_empty")
    item = await _create_item(client, csrf, "Metadata Only", lib_id)

    resp = await client.get("/api/items", params={"library_ids": lib_id})
    assert resp.status_code == 200
    items = resp.json()["items"]
    target = next((i for i in items if i["key"] == item["key"]), None)
    assert target is not None
    assert target["has_asset"] is False


# ---------------------------------------------------------------------------
# has_asset filter param
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_has_asset_true(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/items?has_asset=true returns only items with model/gcode files."""
    csrf = await _login_admin(client, tmp_path)
    lib_id = await _create_lib(client, tmp_path, csrf, "lib_filter_t")

    item_with = await _create_item(client, csrf, "With Model", lib_id)
    item_without = await _create_item(client, csrf, "Without Model", lib_id)

    await _attach_file(db_session, item_with["id"], "model.stl", FileRole.model)
    await _attach_file(db_session, item_without["id"], "images/photo.jpg", FileRole.image)
    db_session.expire_all()

    resp = await client.get("/api/items", params={"library_ids": lib_id, "has_asset": "true"})
    assert resp.status_code == 200
    data = resp.json()
    keys = [i["key"] for i in data["items"]]
    assert item_with["key"] in keys
    assert item_without["key"] not in keys
    # Total count matches filtered result, not all items in library
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_filter_has_asset_false(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/items?has_asset=false returns only items without model/gcode files."""
    csrf = await _login_admin(client, tmp_path)
    lib_id = await _create_lib(client, tmp_path, csrf, "lib_filter_f")

    item_with = await _create_item(client, csrf, "With Model F", lib_id)
    item_without = await _create_item(client, csrf, "Without Model F", lib_id)

    await _attach_file(db_session, item_with["id"], "model.stl", FileRole.model)
    db_session.expire_all()

    resp = await client.get("/api/items", params={"library_ids": lib_id, "has_asset": "false"})
    assert resp.status_code == 200
    data = resp.json()
    keys = [i["key"] for i in data["items"]]
    assert item_without["key"] in keys
    assert item_with["key"] not in keys
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_filter_has_asset_absent_returns_all(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/items (no has_asset param) returns all items regardless of files."""
    csrf = await _login_admin(client, tmp_path)
    lib_id = await _create_lib(client, tmp_path, csrf, "lib_filter_all")

    item_with = await _create_item(client, csrf, "With Model All", lib_id)
    item_without = await _create_item(client, csrf, "Without Model All", lib_id)

    await _attach_file(db_session, item_with["id"], "model.stl", FileRole.model)
    db_session.expire_all()

    resp = await client.get("/api/items", params={"library_ids": lib_id})
    assert resp.status_code == 200
    data = resp.json()
    keys = [i["key"] for i in data["items"]]
    assert item_with["key"] in keys
    assert item_without["key"] in keys
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_filter_has_asset_composes_with_library_filter(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """has_asset filter composes correctly with library filter (AND logic)."""
    csrf = await _login_admin(client, tmp_path)
    lib_a = await _create_lib(client, tmp_path, csrf, "lib_compose_a")
    lib_b = await _create_lib(client, tmp_path, csrf, "lib_compose_b")

    # lib_a: one item with model, one without
    item_a_with = await _create_item(client, csrf, "LibA With Model", lib_a)
    item_a_without = await _create_item(client, csrf, "LibA Without Model", lib_a)
    # lib_b: one item with model
    item_b_with = await _create_item(client, csrf, "LibB With Model", lib_b)

    await _attach_file(db_session, item_a_with["id"], "model.stl", FileRole.model)
    await _attach_file(db_session, item_b_with["id"], "model.stl", FileRole.model)
    db_session.expire_all()

    # Filter: lib_a AND has_asset=true → only item_a_with
    resp = await client.get(
        "/api/items",
        params={"library_ids": lib_a, "has_asset": "true"},
    )
    assert resp.status_code == 200
    data = resp.json()
    keys = [i["key"] for i in data["items"]]
    assert item_a_with["key"] in keys
    assert item_a_without["key"] not in keys
    assert item_b_with["key"] not in keys
    assert data["total"] == 1
