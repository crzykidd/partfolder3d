"""Phase 2 item and library API tests.

Covers:
- Library CRUD (create, list, disable)
- Item create / list / get / update / delete
- Title rename preserves key
- Per-item rescan
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------




async def _login_admin(client: AsyncClient, tmp_path: Path) -> str:
    """Full setup + login flow; returns CSRF token.

    The CSRF token is set as a readable cookie (pf3d_csrf) by the login endpoint.
    """
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
    # CSRF token is in the pf3d_csrf cookie (not in the response body)
    return client.cookies.get("pf3d_csrf", "")


# ---------------------------------------------------------------------------
# Library tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_library(client: AsyncClient, tmp_path: Path) -> None:
    """POST /api/libraries creates a library (admin only)."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "library1")

    resp = await client.post(
        "/api/libraries",
        json={"name": "Main Library", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Main Library"
    assert data["mount_path"] == mount
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_list_libraries(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/libraries lists all libraries."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "lib1")

    await client.post(
        "/api/libraries",
        json={"name": "Lib1", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )

    resp = await client.get("/api/libraries")
    assert resp.status_code == 200
    libs = resp.json()
    assert any(lib["name"] == "Lib1" for lib in libs)


@pytest.mark.asyncio
async def test_create_library_duplicate_mount_path(client: AsyncClient, tmp_path: Path) -> None:
    """Duplicate mount_path returns 409."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "lib_dup")

    await client.post(
        "/api/libraries",
        json={"name": "First", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    resp = await client.post(
        "/api/libraries",
        json={"name": "Second", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_disable_library(client: AsyncClient, tmp_path: Path) -> None:
    """DELETE /api/libraries/{id} disables the library."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "lib_del")

    create_resp = await client.post(
        "/api/libraries",
        json={"name": "ToDelete", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/libraries/{lib_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204

    # Verify it's disabled
    list_resp = await client.get("/api/libraries")
    libs = list_resp.json()
    lib = next((entry for entry in libs if entry["id"] == lib_id), None)
    assert lib is not None
    assert lib["enabled"] is False


# ---------------------------------------------------------------------------
# Item CRUD tests
# ---------------------------------------------------------------------------


async def _create_library_and_item(
    client: AsyncClient,
    tmp_path: Path,
    csrf: str,
    item_title: str = "Ladybug Keychain",
    tags: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a library and an item; return (library_data, item_data)."""
    # Create library with a real directory
    mount = str(tmp_path / "library")
    Path(mount).mkdir(parents=True, exist_ok=True)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Test Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib = lib_resp.json()

    item_resp = await client.post(
        "/api/items",
        json={
            "title": item_title,
            "library_id": lib["id"],
            "description": "A test item",
            "tags": tags or ["keychain", "articulated"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201, item_resp.text
    return lib, item_resp.json()


@pytest.mark.asyncio
async def test_create_item(client: AsyncClient, tmp_path: Path) -> None:
    """POST /api/items creates an item with a stable key and correct slug."""
    csrf = await _login_admin(client, tmp_path)
    lib, item = await _create_library_and_item(client, tmp_path, csrf)

    assert "key" in item
    assert len(item["key"]) == 7
    assert item["title"] == "Ladybug Keychain"
    assert item["slug"].endswith(f"-{item['key']}")
    assert "ladybug-keychain" in item["slug"]
    assert item["library_id"] == lib["id"]


@pytest.mark.asyncio
async def test_create_item_dir_on_disk(client: AsyncClient, tmp_path: Path) -> None:
    """Item directory is created on disk after POST /api/items."""
    csrf = await _login_admin(client, tmp_path)
    lib, item = await _create_library_and_item(client, tmp_path, csrf)

    item_dir = Path(item["dir_path"])
    assert item_dir.exists()
    assert item_dir.is_dir()


@pytest.mark.asyncio
async def test_create_item_sidecar_written(client: AsyncClient, tmp_path: Path) -> None:
    """Sidecar YAML is written to the item directory on create."""
    csrf = await _login_admin(client, tmp_path)
    lib, item = await _create_library_and_item(client, tmp_path, csrf)

    item_dir = Path(item["dir_path"])
    # Sidecar is <slug>.yml
    slug = item["slug"]
    sidecar = item_dir / f"{slug}.yml"
    assert sidecar.exists()

    import yaml

    content = yaml.safe_load(sidecar.read_text())
    assert content["key"] == item["key"]
    assert content["title"] == item["title"]
    assert content["schema_version"] == 1


@pytest.mark.asyncio
async def test_create_item_tags(client: AsyncClient, tmp_path: Path) -> None:
    """Tags are attached to the item on create."""
    csrf = await _login_admin(client, tmp_path)
    lib, item = await _create_library_and_item(
        client, tmp_path, csrf, tags=["keychain", "toy"]
    )

    assert len(item["tags"]) == 2
    tag_names = {t["name"] for t in item["tags"]}
    assert tag_names == {"keychain", "toy"}


@pytest.mark.asyncio
async def test_list_items(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items lists items (paginated)."""
    csrf = await _login_admin(client, tmp_path)
    # Create one library and two items in it to avoid duplicate mount_path 409.
    mount = str(tmp_path / "list_lib")
    Path(mount).mkdir(parents=True, exist_ok=True)
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "List Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201, lib_resp.text
    lib_id = lib_resp.json()["id"]
    for title in ("Item One", "Item Two"):
        r = await client.post(
            "/api/items",
            json={"title": title, "library_id": lib_id, "description": "test"},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 201, r.text

    resp = await client.get("/api/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert "items" in data
    assert "page" in data


@pytest.mark.asyncio
async def test_get_item(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items/{key} returns item detail."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]

    resp = await client.get(f"/api/items/{key}")
    assert resp.status_code == 200
    item = resp.json()
    assert item["key"] == key
    assert item["title"] == "Ladybug Keychain"


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items/{key} returns 404 for unknown key."""
    await _login_admin(client, tmp_path)
    resp = await client.get("/api/items/xxxxxxx")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_item_metadata(client: AsyncClient, tmp_path: Path) -> None:
    """PATCH /api/items/{key} updates description without rename."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]
    original_slug = created["slug"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"description": "Updated description"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["description"] == "Updated description"
    # Slug unchanged (no title change)
    assert updated["slug"] == original_slug


@pytest.mark.asyncio
async def test_rename_item_atomic(client: AsyncClient, tmp_path: Path) -> None:
    """PATCH /api/items/{key} with a new title triggers atomic rename."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf, "Old Title")
    key = created["key"]
    old_dir = Path(created["dir_path"])

    resp = await client.patch(
        f"/api/items/{key}",
        json={"title": "New Title"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    updated = resp.json()

    # Key is preserved
    assert updated["key"] == key

    # New dir exists, old dir gone
    new_dir = Path(updated["dir_path"])
    assert new_dir.exists()
    assert not old_dir.exists()

    # Slug updated
    assert "new-title" in updated["slug"]
    assert updated["slug"].endswith(f"-{key}")


@pytest.mark.asyncio
async def test_rename_preserves_key(client: AsyncClient, tmp_path: Path) -> None:
    """After rename, key is invariant — links survive."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf, "Original")
    key = created["key"]

    await client.patch(
        f"/api/items/{key}",
        json={"title": "Renamed Once"},
        headers={"X-CSRF-Token": csrf},
    )
    resp = await client.patch(
        f"/api/items/{key}",
        json={"title": "Renamed Twice"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["key"] == key

    # Item is still accessible by key
    get_resp = await client.get(f"/api/items/{key}")
    assert get_resp.status_code == 200
    assert get_resp.json()["key"] == key


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient, tmp_path: Path) -> None:
    """DELETE /api/items/{key} moves dir to trash and removes DB row."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]
    item_dir = Path(created["dir_path"])

    resp = await client.delete(
        f"/api/items/{key}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204

    # Item no longer in DB
    get_resp = await client.get(f"/api/items/{key}")
    assert get_resp.status_code == 404

    # Dir moved to trash (not hard-deleted)
    import app.config as cfg_mod

    trash_dir = Path(cfg_mod.settings.DATA_DIR) / "trash"
    assert item_dir.name not in [d.name for d in (trash_dir.parent).rglob("*")]
    # The original path no longer exists
    assert not item_dir.exists()
    # Something in trash has the key in its name
    trash_entries = list(trash_dir.iterdir()) if trash_dir.exists() else []
    assert any(key in entry.name for entry in trash_entries)


@pytest.mark.asyncio
async def test_rescan_item(client: AsyncClient, tmp_path: Path) -> None:
    """POST /api/items/{key}/rescan re-inventories files."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]
    item_dir = Path(created["dir_path"])

    # Add a file to the directory
    (item_dir / "newfile.stl").write_bytes(b"stl content")

    resp = await client.post(
        f"/api/items/{key}/rescan",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    file_paths = [f["path"] for f in data["files"]]
    assert "newfile.stl" in file_paths


@pytest.mark.asyncio
async def test_create_item_with_creator(client: AsyncClient, tmp_path: Path) -> None:
    """POST /api/items with creator info stores creator."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "lib_creator")
    Path(mount).mkdir(parents=True, exist_ok=True)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Creator Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib = lib_resp.json()

    resp = await client.post(
        "/api/items",
        json={
            "title": "Designer Item",
            "library_id": lib["id"],
            "creator": {
                "name": "Jane Maker",
                "profile_url": "https://printables.com/@janemaker",
                "source_site": "printables.com",
            },
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["creator"] is not None
    assert data["creator"]["name"] == "Jane Maker"


# ---------------------------------------------------------------------------
# javascript:-scheme XSS guard on source_url / creator.profile_url
# (audit-2026-07-03 §A [med]).  These fields render into anchor hrefs, incl. the
# unauthenticated public share page — only http(s) may be stored.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox",
        "//evil.example.com",
    ],
)
async def test_patch_item_rejects_dangerous_source_url(
    client: AsyncClient, tmp_path: Path, bad_url: str
) -> None:
    """PATCH with a non-http(s) source_url is rejected at the schema boundary (422)."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"source_url": bad_url},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422, resp.text
    # And the value was not stored.
    get_resp = await client.get(f"/api/items/{key}")
    assert get_resp.json()["source_url"] is None


@pytest.mark.asyncio
async def test_patch_item_accepts_https_source_url(
    client: AsyncClient, tmp_path: Path
) -> None:
    """A legitimate https source_url is accepted and stored."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"source_url": "https://printables.com/model/123"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["source_url"] == "https://printables.com/model/123"


@pytest.mark.asyncio
async def test_patch_item_rejects_dangerous_creator_profile_url(
    client: AsyncClient, tmp_path: Path
) -> None:
    """PATCH with a javascript: creator profile_url is rejected (422)."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(client, tmp_path, csrf)
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"creator": {"name": "Evil", "profile_url": "javascript:alert(document.cookie)"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_item_rejects_dangerous_creator_profile_url(
    client: AsyncClient, tmp_path: Path
) -> None:
    """POST with a javascript: creator profile_url is rejected (422)."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "lib_xss")
    Path(mount).mkdir(parents=True, exist_ok=True)
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "XSS Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib = lib_resp.json()

    resp = await client.post(
        "/api/items",
        json={
            "title": "Evil Item",
            "library_id": lib["id"],
            "creator": {"name": "Evil", "profile_url": "javascript:alert(1)"},
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_update_item_tags(client: AsyncClient, tmp_path: Path) -> None:
    """PATCH /api/items/{key} replaces tags."""
    csrf = await _login_admin(client, tmp_path)
    _, created = await _create_library_and_item(
        client, tmp_path, csrf, tags=["old-tag"]
    )
    key = created["key"]

    resp = await client.patch(
        f"/api/items/{key}",
        json={"tags": ["new-tag-1", "new-tag-2"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    tag_names = {t["name"] for t in resp.json()["tags"]}
    assert tag_names == {"new-tag-1", "new-tag-2"}
    assert "old-tag" not in tag_names
