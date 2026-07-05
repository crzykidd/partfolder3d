"""Router tests for moving item asset(s) between libraries (issue #25).

Covers the single (`POST /api/items/{key}/move`) and bulk (`POST /api/items/move`)
endpoints: a successful move updates ``library_id`` + ``dir_path`` + File rows and
lands the sidecar at the new path; bulk isolates a failing item; and same-library /
disabled-target / bad-key are rejected.

Bulk uses an internal ``SessionLocal()`` per item (per-item isolation), so — like the
bulk-import tests — we monkeypatch ``app.db.SessionLocal`` to reuse the test session.
"""

from __future__ import annotations

import io
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.item import Item
from app.storage.paths import item_dir_path, sidecar_name


async def _setup_and_login(client: AsyncClient) -> str:
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


async def _create_library(client: AsyncClient, csrf: str, name: str, mount: Path) -> dict[str, Any]:
    mount.mkdir(parents=True, exist_ok=True)
    resp = await client.post(
        "/api/libraries",
        json={"name": name, "mount_path": str(mount)},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_item(client: AsyncClient, csrf: str, lib_id: int, title: str) -> dict[str, Any]:
    resp = await client.post(
        "/api/items",
        json={"title": title, "library_id": lib_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _upload_file(client: AsyncClient, csrf: str, key: str, name: str, data: bytes) -> None:
    resp = await client.post(
        f"/api/items/{key}/files",
        files={"file": (name, io.BytesIO(data), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text


def _patch_session_local(db_session: AsyncSession):
    def fake_session_local():
        @asynccontextmanager
        async def _cm():
            yield db_session

        return _cm()

    return fake_session_local


# ---------------------------------------------------------------------------
# Single move
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_move_updates_row_files_and_sidecar(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    csrf = await _setup_and_login(client)
    lib_a = await _create_library(client, csrf, "Lib A", tmp_path / "libA")
    lib_b = await _create_library(client, csrf, "Lib B", tmp_path / "libB")
    item = await _create_item(client, csrf, lib_a["id"], "Movable Widget")
    key = item["key"]
    await _upload_file(client, csrf, key, "model.stl", b"solid model\nendsolid" * 20)

    old_dir = Path(item["dir_path"])
    assert old_dir.exists()

    resp = await client.post(
        f"/api/items/{key}/move",
        json={"target_library_id": lib_b["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    expected_dir = item_dir_path(lib_b["mount_path"], key, "Movable Widget")
    assert data["library_id"] == lib_b["id"]
    assert data["dir_path"] == str(expected_dir)

    # Filesystem: moved, source gone, model + sidecar present at target.
    assert not old_dir.exists()
    assert expected_dir.is_dir()
    assert (expected_dir / "model.stl").exists()
    assert (expected_dir / sidecar_name("Movable Widget", key)).exists()

    # DB row updated.
    db_item = (await db_session.execute(select(Item).where(Item.key == key))).scalar_one()
    assert db_item.library_id == lib_b["id"]
    assert db_item.dir_path == str(expected_dir)

    # File row preserved (path is relative → unchanged).
    file_rows = await db_session.execute(select(File).where(File.item_id == db_item.id))
    files = file_rows.scalars().all()
    assert {f.path for f in files} == {"model.stl"}


@pytest.mark.asyncio
async def test_move_same_library_rejected(
    client: AsyncClient, tmp_path: Path
) -> None:
    csrf = await _setup_and_login(client)
    lib_a = await _create_library(client, csrf, "Lib A", tmp_path / "libA")
    item = await _create_item(client, csrf, lib_a["id"], "Widget")
    resp = await client.post(
        f"/api/items/{item['key']}/move",
        json={"target_library_id": lib_a["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 400
    assert "same" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_move_disabled_target_rejected(
    client: AsyncClient, tmp_path: Path
) -> None:
    csrf = await _setup_and_login(client)
    lib_a = await _create_library(client, csrf, "Lib A", tmp_path / "libA")
    lib_b = await _create_library(client, csrf, "Lib B", tmp_path / "libB")
    item = await _create_item(client, csrf, lib_a["id"], "Widget")
    # Disable target.
    dis = await client.delete(
        f"/api/libraries/{lib_b['id']}", headers={"X-CSRF-Token": csrf}
    )
    assert dis.status_code == 204
    resp = await client.post(
        f"/api/items/{item['key']}/move",
        json={"target_library_id": lib_b["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 400
    assert "disabled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_move_bad_key_rejected(client: AsyncClient, tmp_path: Path) -> None:
    csrf = await _setup_and_login(client)
    lib_a = await _create_library(client, csrf, "Lib A", tmp_path / "libA")
    lib_b = await _create_library(client, csrf, "Lib B", tmp_path / "libB")
    _ = lib_a
    resp = await client.post(
        "/api/items/doesnotexist/move",
        json={"target_library_id": lib_b["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_move_nonexistent_target_rejected(
    client: AsyncClient, tmp_path: Path
) -> None:
    csrf = await _setup_and_login(client)
    lib_a = await _create_library(client, csrf, "Lib A", tmp_path / "libA")
    item = await _create_item(client, csrf, lib_a["id"], "Widget")
    resp = await client.post(
        f"/api/items/{item['key']}/move",
        json={"target_library_id": 99999},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Bulk move
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_move_success(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csrf = await _setup_and_login(client)
    lib_a = await _create_library(client, csrf, "Lib A", tmp_path / "libA")
    lib_b = await _create_library(client, csrf, "Lib B", tmp_path / "libB")
    item1 = await _create_item(client, csrf, lib_a["id"], "Alpha")
    item2 = await _create_item(client, csrf, lib_a["id"], "Beta")

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _patch_session_local(db_session))

    resp = await client.post(
        "/api/items/move",
        json={"keys": [item1["key"], item2["key"]], "target_library_id": lib_b["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    assert data["moved"] == 2
    assert data["skipped"] == []
    assert data["errors"] == []

    for it, title in ((item1, "Alpha"), (item2, "Beta")):
        expected = item_dir_path(lib_b["mount_path"], it["key"], title)
        assert expected.is_dir()
        assert not Path(it["dir_path"]).exists()
        row = (
            await db_session.execute(select(Item).where(Item.key == it["key"]))
        ).scalar_one()
        assert row.library_id == lib_b["id"]
        assert row.dir_path == str(expected)


@pytest.mark.asyncio
async def test_bulk_move_isolates_failing_item(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad key in the batch must not block the good items."""
    csrf = await _setup_and_login(client)
    lib_a = await _create_library(client, csrf, "Lib A", tmp_path / "libA")
    lib_b = await _create_library(client, csrf, "Lib B", tmp_path / "libB")
    good = await _create_item(client, csrf, lib_a["id"], "Good")

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _patch_session_local(db_session))

    resp = await client.post(
        "/api/items/move",
        json={"keys": [good["key"], "nope404"], "target_library_id": lib_b["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    assert data["moved"] == 1
    reasons = {s["key"]: s["reason"] for s in data["skipped"]}
    assert reasons.get("nope404") == "not_found"

    row = (
        await db_session.execute(select(Item).where(Item.key == good["key"]))
    ).scalar_one()
    assert row.library_id == lib_b["id"]


@pytest.mark.asyncio
async def test_bulk_move_same_library_skipped(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csrf = await _setup_and_login(client)
    lib_a = await _create_library(client, csrf, "Lib A", tmp_path / "libA")
    await _create_library(client, csrf, "Lib B", tmp_path / "libB")
    item = await _create_item(client, csrf, lib_a["id"], "Stayput")

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _patch_session_local(db_session))

    resp = await client.post(
        "/api/items/move",
        json={"keys": [item["key"]], "target_library_id": lib_a["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["moved"] == 0
    assert data["skipped"][0]["reason"] == "same_library"
