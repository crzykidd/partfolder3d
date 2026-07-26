"""Tests for issue #47 — edit an existing item's description + tags in-app.

Covers PATCH /api/items/{key} (description + tag add/remove), the tag
pending-vs-auto-approve reconciliation on that path, and — the load-bearing
part — that a description/tag edit does NOT get flagged as sidecar drift on
the next reconcile scan (the same write-through-in-one-operation discipline
documented for the v0.7.2 corruption-vs-legit-edit work).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _login_admin(client: AsyncClient, tmp_path: Path) -> str:
    """Full setup + login flow; returns CSRF token (mirrors test_phase2_items.py)."""
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


async def _create_library_and_item(
    client: AsyncClient,
    tmp_path: Path,
    csrf: str,
    item_title: str = "Edit Target Widget",
    tags: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a library and an item; return (library_data, item_data)."""
    mount = str(tmp_path / "library")
    Path(mount).mkdir(parents=True, exist_ok=True)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Edit Test Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib = lib_resp.json()

    item_resp = await client.post(
        "/api/items",
        json={
            "title": item_title,
            "library_id": lib["id"],
            "description": "Original description",
            "tags": tags if tags is not None else ["old-tag"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201, item_resp.text
    return lib, item_resp.json()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_description_and_tags_happy_path(
    client: AsyncClient, tmp_path: Path
) -> None:
    """PATCH updates description and replaces tags; both write through to the sidecar."""
    from app.storage.sidecar import read_sidecar  # noqa: PLC0415

    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"description": "Edited description", "tags": ["old-tag", "new-tag"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["description"] == "Edited description"
    assert {t["name"] for t in updated["tags"]} == {"old-tag", "new-tag"}

    # Sidecar on disk reflects the edit (write-through).
    item_dir = Path(updated["dir_path"])
    sc = read_sidecar(item_dir, updated["title"], key)
    assert sc is not None
    assert sc.description == "Edited description"
    assert set(sc.tags) == {"old-tag", "new-tag"}


@pytest.mark.asyncio
async def test_update_item_tags_add_and_remove(
    client: AsyncClient, tmp_path: Path
) -> None:
    """The frontend sends the full desired tag list; PATCH removes/adds accordingly."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(
        client, tmp_path, csrf, tags=["keep-me", "remove-me"]
    )
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"tags": ["keep-me", "add-me"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    tag_names = {t["name"] for t in resp.json()["tags"]}
    assert tag_names == {"keep-me", "add-me"}
    assert "remove-me" not in tag_names


# ---------------------------------------------------------------------------
# Auth / CSRF rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_item_requires_auth(client: AsyncClient) -> None:
    """PATCH without a session is rejected (401) — no anonymous item edits.

    get_current_user is evaluated before the item lookup, so a nonexistent key
    is enough to prove auth is checked first (mirrors
    test_reviews_bulk_endpoints_require_auth's pattern).
    """
    resp = await client.patch(
        "/api/items/xxxxxxx",
        json={"description": "Should not be applied"},
        headers={"X-CSRF-Token": "fake"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_item_requires_csrf(client: AsyncClient, tmp_path: Path) -> None:
    """PATCH with a valid session but no CSRF header is rejected (403)."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"description": "Should not be applied"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tag pending vs auto-approve (reuses the import-commit reconciliation gate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_item_new_tag_defaults_to_pending(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """A brand-new tag name added via item edit lands `pending` by default (#31 gate)."""
    from app.models.tag import Tag, TagStatus  # noqa: PLC0415

    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf, tags=[])
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"tags": ["brand-new-tag"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    out_tags = resp.json()["tags"]
    assert len(out_tags) == 1
    assert out_tags[0]["status"] == "pending"

    res = await db_session.execute(select(Tag).where(Tag.name == "brand-new-tag"))
    tag = res.scalar_one()
    assert tag.status == TagStatus.pending


@pytest.mark.asyncio
async def test_update_item_new_tag_active_when_auto_approve_on(
    client: AsyncClient, tmp_path: Path
) -> None:
    """With tags.auto_approve ON, a brand-new tag added via item edit lands active."""
    csrf = await _login_admin(client, tmp_path)

    setting_resp = await client.put(
        "/api/settings/tags.auto_approve",
        json={"value": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert setting_resp.status_code == 200, setting_resp.text

    _, created = await _create_library_and_item(client, tmp_path, csrf, tags=[])
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"tags": ["auto-approved-edit-tag"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    out_tags = resp.json()["tags"]
    assert len(out_tags) == 1
    assert out_tags[0]["status"] == "active"


@pytest.mark.asyncio
async def test_update_item_existing_tag_keeps_its_status(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """Re-adding an already-existing tag (any status) does not change its status."""
    from app.models.tag import Tag, TagStatus  # noqa: PLC0415

    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf, tags=[])
    key = created["key"]

    # Seed a pre-existing PENDING tag directly (e.g. left over from an import).
    pending_tag = Tag(name="already-pending", status=TagStatus.pending)
    db_session.add(pending_tag)
    await db_session.flush()

    resp = await client.patch(
        f"/api/items/{key}",
        json={"tags": ["already-pending"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    out_tags = resp.json()["tags"]
    assert len(out_tags) == 1
    # Attaching an existing tag must not silently promote it to active.
    assert out_tags[0]["status"] == "pending"


# ---------------------------------------------------------------------------
# The crux: an edit must NOT be flagged as sidecar drift on the next scan.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_after_edit_not_flagged_as_drift(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """A description + tag edit via the item PATCH endpoint is a legit local edit.

    The next reconcile scan must NOT raise a sidecar `conflict` Issue nor queue a
    `sidecar_pulled_to_db` ReviewItem — the PATCH write-through already left the
    DB `updated_at`, the sidecar's own `updated_at` field, and the sidecar file's
    on-disk mtime in sync (within reconcile.SIDECAR_SYNC_TOLERANCE_SECONDS), the
    same discipline the v0.7.2 corruption-vs-legit-edit fix relies on for model
    files.
    """
    from app.models.item import Item  # noqa: PLC0415
    from app.worker.reconcile import DEFAULT_MODES, reconcile_one_item  # noqa: PLC0415

    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf, tags=["old-tag"])
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"description": "Edited via the item page", "tags": ["old-tag", "new-tag"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text

    # Load the same ORM row the API just wrote (client/db_session share a session).
    res = await db_session.execute(select(Item).where(Item.key == key))
    item = res.scalar_one()

    result = await reconcile_one_item(
        db_session,
        item,
        mode_settings=DEFAULT_MODES,  # sidecar_sync defaults to "review" — the strict path
        source="auto",
    )

    assert result.issues_created == []
    assert result.review_items_created == []
    assert not any(
        c.get("behavior") == "sidecar_sync" for c in result.changes_applied
    ), "an in-sync sidecar should not trigger any sidecar_sync change either"
