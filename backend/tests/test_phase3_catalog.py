"""Phase 3 catalog API tests.

Covers:
- Favorites (star / unstar / list / filter)
- Full-text search (q param)
- Tag filter (AND)
- Sort options
- Tag list endpoint + tag tree
- Creator list / creator items
- My Creations endpoint
- Path prefix (get / set)
- Set default image
- File download (path traversal guard)
- ZIP bundle queue (create / poll — no real worker in tests)
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _login_admin(client: AsyncClient, tmp_path: Path) -> str:
    """Setup instance + login as admin; returns CSRF token."""
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


async def _create_lib_and_item(
    client: AsyncClient,
    tmp_path: Path,
    csrf: str,
    title: str = "Test Item",
    tags: list[str] | None = None,
    description: str | None = None,
    creator: dict[str, Any] | None = None,
    mount_suffix: str = "library",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a library and an item; return (library, item)."""
    mount = str(tmp_path / mount_suffix)
    Path(mount).mkdir(parents=True, exist_ok=True)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201, lib_resp.text
    lib = lib_resp.json()

    payload: dict[str, Any] = {
        "title": title,
        "library_id": lib["id"],
        "tags": tags or [],
    }
    if description is not None:
        payload["description"] = description
    if creator is not None:
        payload["creator"] = creator

    item_resp = await client.post(
        "/api/items",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201, item_resp.text
    return lib, item_resp.json()


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_star_item(client: AsyncClient, tmp_path: Path) -> None:
    """POST /api/items/{key}/favorite stars an item."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    resp = await client.post(
        f"/api/items/{key}/favorite",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["favorited"] is True
    assert data["item_id"] == item["id"]


@pytest.mark.asyncio
async def test_star_idempotent(client: AsyncClient, tmp_path: Path) -> None:
    """Starring twice is idempotent (no 409)."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    for _ in range(2):
        resp = await client.post(
            f"/api/items/{key}/favorite",
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_unstar_item(client: AsyncClient, tmp_path: Path) -> None:
    """DELETE /api/items/{key}/favorite unstars an item."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    await client.post(f"/api/items/{key}/favorite", headers={"X-CSRF-Token": csrf})
    del_resp = await client.delete(
        f"/api/items/{key}/favorite",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204, del_resp.text


@pytest.mark.asyncio
async def test_unstar_idempotent(client: AsyncClient, tmp_path: Path) -> None:
    """Unstarring a non-starred item is idempotent (no 404)."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    resp = await client.delete(
        f"/api/items/{key}/favorite",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_list_favorites(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/me/favorites lists starred items."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    # Not starred yet
    resp = await client.get("/api/me/favorites")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Star it
    await client.post(f"/api/items/{key}/favorite", headers={"X-CSRF-Token": csrf})
    resp2 = await client.get("/api/me/favorites")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["total"] == 1
    assert data["items"][0]["key"] == key


@pytest.mark.asyncio
async def test_list_items_favorited_filter(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items?favorited=true returns only starred items."""
    csrf = await _login_admin(client, tmp_path)
    # Create two items; star only one
    mount = str(tmp_path / "libfav")
    Path(mount).mkdir(parents=True, exist_ok=True)
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "FavLib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib_id = lib_resp.json()["id"]

    keys = []
    for title in ("Item A", "Item B"):
        r = await client.post(
            "/api/items",
            json={"title": title, "library_id": lib_id},
            headers={"X-CSRF-Token": csrf},
        )
        keys.append(r.json()["key"])

    # Star only the first
    await client.post(f"/api/items/{keys[0]}/favorite", headers={"X-CSRF-Token": csrf})

    resp = await client.get("/api/items", params={"favorited": "true"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    returned_keys = [i["key"] for i in data["items"]]
    assert keys[0] in returned_keys
    assert keys[1] not in returned_keys


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_items_search_q(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items?q=... returns matching items."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "search_lib")
    Path(mount).mkdir(parents=True, exist_ok=True)
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "SLib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib_id = lib_resp.json()["id"]

    await client.post(
        "/api/items",
        json={
            "title": "Articulated Dragon",
            "library_id": lib_id,
            "description": "A dragon with joints",
        },
        headers={"X-CSRF-Token": csrf},
    )
    await client.post(
        "/api/items",
        json={"title": "Simple Cube", "library_id": lib_id, "description": "Just a cube"},
        headers={"X-CSRF-Token": csrf},
    )

    resp = await client.get("/api/items", params={"q": "dragon"})
    assert resp.status_code == 200
    data = resp.json()
    titles = [i["title"] for i in data["items"]]
    assert "Articulated Dragon" in titles
    assert "Simple Cube" not in titles


@pytest.mark.asyncio
async def test_list_items_tag_filter(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items?tags=... filters items by AND logic."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "taglib")
    Path(mount).mkdir(parents=True, exist_ok=True)
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "TLib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib_id = lib_resp.json()["id"]

    await client.post(
        "/api/items",
        json={"title": "Both Tags", "library_id": lib_id, "tags": ["alpha", "beta"]},
        headers={"X-CSRF-Token": csrf},
    )
    await client.post(
        "/api/items",
        json={"title": "Only Alpha", "library_id": lib_id, "tags": ["alpha"]},
        headers={"X-CSRF-Token": csrf},
    )
    await client.post(
        "/api/items",
        json={"title": "Only Beta", "library_id": lib_id, "tags": ["beta"]},
        headers={"X-CSRF-Token": csrf},
    )

    # AND filter: must have both alpha AND beta
    resp = await client.get("/api/items", params=[("tags", "alpha"), ("tags", "beta")])
    assert resp.status_code == 200
    data = resp.json()
    titles = [i["title"] for i in data["items"]]
    assert "Both Tags" in titles
    assert "Only Alpha" not in titles
    assert "Only Beta" not in titles


@pytest.mark.asyncio
async def test_list_items_sort_title(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items?sort=title_asc returns items in title order."""
    csrf = await _login_admin(client, tmp_path)
    mount = str(tmp_path / "sortlib")
    Path(mount).mkdir(parents=True, exist_ok=True)
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "SortLib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    lib_id = lib_resp.json()["id"]

    for title in ("Zebra", "Apple", "Mango"):
        await client.post(
            "/api/items",
            json={"title": title, "library_id": lib_id},
            headers={"X-CSRF-Token": csrf},
        )

    resp = await client.get("/api/items", params={"sort": "title_asc", "library_id": lib_id})
    assert resp.status_code == 200
    titles = [i["title"] for i in resp.json()["items"]]
    assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# Tag endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tags(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/tags returns tags with popularity counts."""
    csrf = await _login_admin(client, tmp_path)
    await _create_lib_and_item(client, tmp_path, csrf, tags=["keychain", "articulated"])

    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert "tags" in data
    tag_names = [t["name"] for t in data["tags"]]
    assert "keychain" in tag_names
    assert "articulated" in tag_names


@pytest.mark.asyncio
async def test_list_tags_filter(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/tags?q=key filters by name prefix."""
    csrf = await _login_admin(client, tmp_path)
    await _create_lib_and_item(client, tmp_path, csrf, tags=["keychain", "toy"])

    resp = await client.get("/api/tags", params={"q": "key"})
    assert resp.status_code == 200
    tags = resp.json()["tags"]
    assert all("key" in t["name"] for t in tags)


@pytest.mark.asyncio
async def test_tag_tree(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/tags/tree returns a tree structure."""
    csrf = await _login_admin(client, tmp_path)
    await _create_lib_and_item(client, tmp_path, csrf, tags=["keychain"])

    resp = await client.get("/api/tags/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert "depth" in data
    assert "nodes" in data
    assert isinstance(data["nodes"], list)


@pytest.mark.asyncio
async def test_tag_tree_depth_override(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/tags/tree?depth=2 honours the override."""
    resp = await client.get("/api/tags/tree", params={"depth": "2"})
    assert resp.status_code == 200
    assert resp.json()["depth"] == 2


# ---------------------------------------------------------------------------
# Creator endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_creators(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/creators lists creators that have items."""
    csrf = await _login_admin(client, tmp_path)
    await _create_lib_and_item(
        client, tmp_path, csrf,
        creator={"name": "Jane Maker", "profile_url": None, "source_site": "printables.com"},
    )

    resp = await client.get("/api/creators")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    creator_names = [c["name"] for c in data["creators"]]
    assert "Jane Maker" in creator_names


@pytest.mark.asyncio
async def test_get_creator(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/creators/{id} returns creator detail with item count."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(
        client, tmp_path, csrf,
        creator={"name": "Bob Builder", "profile_url": None, "source_site": None},
    )
    creator_id = item["creator"]["id"]

    resp = await client.get(f"/api/creators/{creator_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Bob Builder"
    assert data["item_count"] == 1


@pytest.mark.asyncio
async def test_get_creator_not_found(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/creators/99999 returns 404."""
    await _login_admin(client, tmp_path)
    resp = await client.get("/api/creators/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_creator_items(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/creators/{id}/items lists items by that creator."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(
        client, tmp_path, csrf,
        creator={"name": "Alice Artist", "profile_url": None, "source_site": None},
    )
    creator_id = item["creator"]["id"]

    resp = await client.get(f"/api/creators/{creator_id}/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["key"] == item["key"]
    assert data["creator"]["name"] == "Alice Artist"


# ---------------------------------------------------------------------------
# My Creations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_my_creations_empty(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/me/creations returns empty when no items linked to user."""
    await _login_admin(client, tmp_path)
    resp = await client.get("/api/me/creations")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_my_creations_with_linked_creator(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/me/creations returns items whose Creator.user_id == current user."""
    from sqlalchemy import update as sa_update  # noqa: PLC0415

    from app.models.creator import Creator  # noqa: PLC0415

    csrf = await _login_admin(client, tmp_path)

    # Get current user id
    me_resp = await client.get("/api/auth/me")
    user_id = me_resp.json()["user_id"]

    # Create an item with a creator.
    # (In Phase 5 the import wizard sets Creator.user_id via the "my own design" toggle;
    # here we patch it directly via the test session to test the query logic.)
    _, item = await _create_lib_and_item(
        client, tmp_path, csrf,
        creator={"name": "Self Designer", "profile_url": None, "source_site": None},
    )
    creator_id = item["creator"]["id"]

    # Patch Creator.user_id using the shared test session (same transaction as client).
    await db_session.execute(
        sa_update(Creator)
        .where(Creator.id == creator_id)
        .values(user_id=user_id)
    )
    # Expire all cached ORM instances so the next SELECT re-reads from DB.
    db_session.expire_all()

    resp = await client.get("/api/me/creations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["key"] == item["key"]


# ---------------------------------------------------------------------------
# Path prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_path_prefix_default(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/me/path-prefix returns null by default."""
    await _login_admin(client, tmp_path)
    resp = await client.get("/api/me/path-prefix")
    assert resp.status_code == 200
    assert resp.json()["path_prefix"] is None


@pytest.mark.asyncio
async def test_set_path_prefix(client: AsyncClient, tmp_path: Path) -> None:
    """PUT /api/me/path-prefix sets the user's path prefix."""
    csrf = await _login_admin(client, tmp_path)
    resp = await client.put(
        "/api/me/path-prefix",
        json={"path_prefix": r"C:\prints\\"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["path_prefix"] == r"C:\prints\\"

    # Verify it persists
    get_resp = await client.get("/api/me/path-prefix")
    assert get_resp.json()["path_prefix"] == r"C:\prints\\"


@pytest.mark.asyncio
async def test_clear_path_prefix(client: AsyncClient, tmp_path: Path) -> None:
    """PUT /api/me/path-prefix with null clears the prefix."""
    csrf = await _login_admin(client, tmp_path)
    # Set first
    await client.put(
        "/api/me/path-prefix",
        json={"path_prefix": "/mnt/library"},
        headers={"X-CSRF-Token": csrf},
    )
    # Clear
    resp = await client.put(
        "/api/me/path-prefix",
        json={"path_prefix": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["path_prefix"] is None


# ---------------------------------------------------------------------------
# Set default image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_default_image_wrong_item(client: AsyncClient, tmp_path: Path) -> None:
    """PATCH /api/items/{key}/default-image returns 404 for non-existent image."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    resp = await client.patch(
        f"/api/items/{key}/default-image",
        json={"image_id": 999999},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_default_image_not_found_item(client: AsyncClient, tmp_path: Path) -> None:
    """PATCH /api/items/badkey/default-image returns 404."""
    csrf = await _login_admin(client, tmp_path)
    resp = await client.patch(
        "/api/items/notexist/default-image",
        json={"image_id": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# File download — path traversal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_download_traversal_guard(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items/{key}/files/..%2F..%2Fetc%2Fpasswd returns 400.

    The percent-encoded slashes bypass URL normalization at the httpx/ASGI layer so
    the traversal string reaches the handler, which must reject it with 400.
    """
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    # Use encoded slashes so httpx doesn't normalize the URL (which would route to
    # a non-existent path and return 404 before hitting our traversal check).
    resp = await client.get(f"/api/items/{key}/files/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_file_download_not_found(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items/{key}/files/nonexistent.stl returns 404."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    resp = await client.get(f"/api/items/{key}/files/nonexistent.stl")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_file_download_existing_file(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items/{key}/files/<file> returns 200 for an existing file."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]
    item_dir = Path(item["dir_path"])

    # Place a test file in the item directory
    (item_dir / "test_model.stl").write_bytes(b"solid test\nendsolid test\n")

    resp = await client.get(f"/api/items/{key}/files/test_model.stl")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# ZIP bundle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zip_bundle_create(client: AsyncClient, tmp_path: Path) -> None:
    """POST /api/items/{key}/zip creates a pending bundle."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    resp = await client.post(
        f"/api/items/{key}/zip",
        headers={"X-CSRF-Token": csrf},
    )
    # May return 200 (bundle created) or 500 if Redis is not available
    # In test env there's no real Redis, so the enqueue fails gracefully.
    # The bundle is still created; status should be pending.
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_zip_bundle_idempotent(client: AsyncClient, tmp_path: Path) -> None:
    """POST /api/items/{key}/zip twice returns the same pending bundle."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    r1 = await client.post(f"/api/items/{key}/zip", headers={"X-CSRF-Token": csrf})
    r2 = await client.post(f"/api/items/{key}/zip", headers={"X-CSRF-Token": csrf})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Should reuse the same pending bundle
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_zip_bundle_poll_pending(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items/{key}/zip/{id} returns pending status while in progress."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    create_resp = await client.post(
        f"/api/items/{key}/zip",
        headers={"X-CSRF-Token": csrf},
    )
    bundle_id = create_resp.json()["id"]

    poll_resp = await client.get(f"/api/items/{key}/zip/{bundle_id}")
    assert poll_resp.status_code == 200
    assert poll_resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_zip_bundle_poll_invalid_id(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items/{key}/zip/invalid-uuid returns 400."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    resp = await client.get(f"/api/items/{key}/zip/not-a-uuid")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zip_bundle_not_found(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items/{key}/zip/{random-uuid} returns 404."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(client, tmp_path, csrf)
    key = item["key"]

    resp = await client.get(f"/api/items/{key}/zip/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Item list enrichment (Phase 3 additions to list_items)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_items_includes_enrichment(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/items returns tag_names and favorited flag."""
    csrf = await _login_admin(client, tmp_path)
    _, item = await _create_lib_and_item(
        client, tmp_path, csrf,
        tags=["gadget", "prototype"],
    )

    resp = await client.get("/api/items")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1

    target = next((i for i in items if i["key"] == item["key"]), None)
    assert target is not None
    assert set(target["tag_names"]) == {"gadget", "prototype"}
    assert target["favorited"] is False
