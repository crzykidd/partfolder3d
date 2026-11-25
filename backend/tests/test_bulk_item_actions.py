"""Bulk item actions: print-records, tags, delete, rescan (multi-select backend).

Bulk tags/delete/rescan use an internal ``SessionLocal()`` per item (per-item isolation),
so — like the bulk-move tests — ``app.db.SessionLocal`` is monkeypatched to reuse the
test session.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.print_record import PrintRecord
from app.models.tag import Tag, TagStatus


async def _login(client: AsyncClient) -> str:
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


async def _make_items(
    client: AsyncClient, csrf: str, tmp_path: Path, n: int = 2, tags: list[str] | None = None
) -> list[dict[str, Any]]:
    mount = tmp_path / "library"
    mount.mkdir(parents=True, exist_ok=True)
    lib = (
        await client.post(
            "/api/libraries",
            json={"name": "Bulk Lib", "mount_path": str(mount)},
            headers={"X-CSRF-Token": csrf},
        )
    ).json()
    items = []
    for i in range(n):
        resp = await client.post(
            "/api/items",
            json={"title": f"Bulk Widget {i}", "library_id": lib["id"], "tags": tags or []},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201, resp.text
        items.append(resp.json())
    return items


def _patch_session_local(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> None:
    def fake_session_local():
        @asynccontextmanager
        async def _cm():
            yield db_session

        return _cm()

    monkeypatch.setattr("app.db.SessionLocal", fake_session_local)


def _sidecar_tags(item: dict[str, Any]) -> set[str]:
    sidecar = Path(item["dir_path"]) / f"{item['slug']}.yml"
    doc = yaml.safe_load(sidecar.read_text())
    return set(doc.get("tags") or [])


# ---------------------------------------------------------------------------
# bulk-print-records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_print_records_creates_one_per_item(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    csrf = await _login(client)
    items = await _make_items(client, csrf, tmp_path, 2)
    keys = [i["key"] for i in items]

    resp = await client.post(
        "/api/items/bulk-print-records",
        json={
            "keys": keys + [keys[0]],  # duplicate is de-duplicated
            "record": {"note": "batch", "printer": "MK4", "success": True, "rating": 4},
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["created"] == 2
    assert [r["item_key"] for r in data["records"]] == keys
    assert all(r["note"] == "batch" and r["printer"] == "MK4" for r in data["records"])
    assert all(r["logged_by_id"] is not None for r in data["records"])

    count = (await db_session.execute(select(func.count(PrintRecord.id)))).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_bulk_print_records_missing_key_creates_nothing(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    csrf = await _login(client)
    items = await _make_items(client, csrf, tmp_path, 1)

    resp = await client.post(
        "/api/items/bulk-print-records",
        json={"keys": [items[0]["key"], "nope-key"], "record": {"note": "x"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "Items not found."
    assert body["missing"] == ["nope-key"]
    count = (await db_session.execute(select(func.count(PrintRecord.id)))).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_bulk_print_records_validation_and_csrf(
    client: AsyncClient, tmp_path: Path
) -> None:
    csrf = await _login(client)
    items = await _make_items(client, csrf, tmp_path, 1)
    key = items[0]["key"]

    resp = await client.post(
        "/api/items/bulk-print-records",
        json={"keys": [], "record": {}},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422
    resp = await client.post(
        "/api/items/bulk-print-records",
        json={"keys": [key], "record": {"visibility": "weird"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422
    resp = await client.post(
        "/api/items/bulk-print-records",
        json={"keys": [key], "record": {}},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# bulk-tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_tags_add_remove_semantics_and_sidecar(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = await _login(client)
    items = await _make_items(client, csrf, tmp_path, 2, tags=["keep", "drop"])
    keys = [i["key"] for i in items]
    _patch_session_local(monkeypatch, db_session)

    resp = await client.post(
        "/api/items/bulk-tags",
        json={"keys": keys, "add": ["fresh", "keep"], "remove": ["drop"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"succeeded": keys, "failed": []}

    for it in items:
        detail = (await client.get(f"/api/items/{it['key']}")).json()
        assert {t["name"] for t in detail["tags"]} == {"keep", "fresh"}
        assert _sidecar_tags(it) == {"keep", "fresh"}

    # Brand-new tag lands pending (auto_approve off); pre-existing keeps its status.
    fresh = (await db_session.execute(select(Tag).where(Tag.name == "fresh"))).scalar_one()
    assert fresh.status == TagStatus.pending


@pytest.mark.asyncio
async def test_bulk_tags_new_tag_active_when_auto_approve(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = await _login(client)
    await client.put(
        "/api/settings/tags.auto_approve",
        json={"value": True},
        headers={"X-CSRF-Token": csrf},
    )
    items = await _make_items(client, csrf, tmp_path, 1)
    _patch_session_local(monkeypatch, db_session)

    resp = await client.post(
        "/api/items/bulk-tags",
        json={"keys": [items[0]["key"]], "add": ["auto-tag"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    tag = (await db_session.execute(select(Tag).where(Tag.name == "auto-tag"))).scalar_one()
    assert tag.status == TagStatus.active


@pytest.mark.asyncio
async def test_bulk_tags_partial_success_and_unchanged(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = await _login(client)
    items = await _make_items(client, csrf, tmp_path, 1, tags=["a"])
    key = items[0]["key"]
    _patch_session_local(monkeypatch, db_session)

    resp = await client.post(
        "/api/items/bulk-tags",
        json={"keys": [key, "missing-key"], "add": ["a"]},  # no-op for existing item
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["succeeded"] == [key]
    assert data["failed"] == [{"key": "missing-key", "error": "Item not found."}]


@pytest.mark.asyncio
async def test_bulk_tags_validation(client: AsyncClient, tmp_path: Path) -> None:
    csrf = await _login(client)
    h = {"X-CSRF-Token": csrf}
    r = await client.post("/api/items/bulk-tags", json={"keys": ["k"]}, headers=h)
    assert r.status_code == 422  # neither add nor remove
    r = await client.post(
        "/api/items/bulk-tags", json={"keys": ["k"], "add": ["  "], "remove": []}, headers=h
    )
    assert r.status_code == 422
    r = await client.post("/api/items/bulk-tags", json={"keys": [], "add": ["x"]}, headers=h)
    assert r.status_code == 422
    r = await client.post(
        "/api/items/bulk-tags",
        json={"keys": [f"k{i}" for i in range(501)], "add": ["x"]},
        headers=h,
    )
    assert r.status_code == 422
    r = await client.post("/api/items/bulk-tags", json={"keys": ["k"], "add": ["x"]})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_patch_item_tags_replace_still_works(client: AsyncClient, tmp_path: Path) -> None:
    """Regression: PATCH /{key} tag REPLACE semantics survive the shared-helper refactor."""
    csrf = await _login(client)
    items = await _make_items(client, csrf, tmp_path, 1, tags=["old"])
    resp = await client.patch(
        f"/api/items/{items[0]['key']}",
        json={"tags": ["n1", "n2"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert {t["name"] for t in resp.json()["tags"]} == {"n1", "n2"}


# ---------------------------------------------------------------------------
# bulk-delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_delete_partial_success(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = await _login(client)
    items = await _make_items(client, csrf, tmp_path, 2)
    keys = [i["key"] for i in items]
    _patch_session_local(monkeypatch, db_session)

    resp = await client.post(
        "/api/items/bulk-delete",
        json={"keys": keys + ["ghost", keys[0]]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["succeeded"] == keys
    assert data["failed"] == [{"key": "ghost", "error": "Item not found."}]
    for it in items:
        assert not Path(it["dir_path"]).exists()
    remaining = (
        await db_session.execute(select(func.count(Item.id)).where(Item.key.in_(keys)))
    ).scalar_one()
    assert remaining == 0


@pytest.mark.asyncio
async def test_bulk_delete_validation(client: AsyncClient, tmp_path: Path) -> None:
    csrf = await _login(client)
    h = {"X-CSRF-Token": csrf}
    r = await client.post("/api/items/bulk-delete", json={"keys": []}, headers=h)
    assert r.status_code == 422
    r = await client.post(
        "/api/items/bulk-delete", json={"keys": [f"k{i}" for i in range(501)]}, headers=h
    )
    assert r.status_code == 422
    assert (await client.post("/api/items/bulk-delete", json={"keys": ["k"]})).status_code in (
        401,
        403,
    )


# ---------------------------------------------------------------------------
# bulk-rescan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_rescan_partial_success(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = await _login(client)
    items = await _make_items(client, csrf, tmp_path, 2)
    keys = [i["key"] for i in items]
    # A stray file the rescan should pick up.
    (Path(items[0]["dir_path"]) / "extra.stl").write_bytes(b"solid x\nendsolid x\n" * 5)
    _patch_session_local(monkeypatch, db_session)

    resp = await client.post(
        "/api/items/bulk-rescan",
        json={"keys": keys + ["ghost"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["succeeded"] == keys
    assert data["failed"] == [{"key": "ghost", "error": "Item not found."}]
    detail = (await client.get(f"/api/items/{keys[0]}")).json()
    assert any(f["path"] == "extra.stl" for f in detail["files"])


@pytest.mark.asyncio
async def test_bulk_rescan_cap_and_csrf(client: AsyncClient, tmp_path: Path) -> None:
    csrf = await _login(client)
    h = {"X-CSRF-Token": csrf}
    r = await client.post("/api/items/bulk-rescan", json={"keys": []}, headers=h)
    assert r.status_code == 422
    r = await client.post(
        "/api/items/bulk-rescan", json={"keys": [f"k{i}" for i in range(101)]}, headers=h
    )
    assert r.status_code == 422
    assert (await client.post("/api/items/bulk-rescan", json={"keys": ["k"]})).status_code in (
        401,
        403,
    )
