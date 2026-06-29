"""Tests for per-library × per-OS path prefixes (Phase 17 / migration 0017).

Covers:
  - GET /api/me/path-prefixes: empty map for fresh user
  - PUT /api/me/path-prefixes: round-trip persists the map
  - PUT filters out unknown library IDs
  - PUT with empty map clears all prefixes
  - Auth required (401 on unauthenticated requests)
  - CSRF required (403 without CSRF token)
  - Migration helper: infer_prefix_map pure-function unit tests
  - End-to-end migration simulation via DB + API
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.path_prefix_utils import infer_prefix_map

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_setup(client: AsyncClient) -> str:
    """Create admin account, log in, return CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "adminpass123",
        },
    )
    await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    return client.cookies.get("pf3d_csrf", "")


async def _create_library(
    client: AsyncClient,
    csrf: str,
    name: str = "Main",
    mount: str = "/library/main",
) -> int:
    """Create a library and return its id."""
    resp = await client.post(
        "/api/libraries",
        json={"name": name, "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code in (200, 201), resp.text
    return int(resp.json()["id"])


# ---------------------------------------------------------------------------
# Migration helper unit tests (pure function — no DB needed)
# ---------------------------------------------------------------------------


def test_infer_prefix_map_posix() -> None:
    """Posix prefix assigns os_key=posix for all libraries."""
    result = infer_prefix_map("/mnt/nas/prints/", [1, 2])
    assert result == {
        "1": {"posix": "/mnt/nas/prints/", "windows": None},
        "2": {"posix": "/mnt/nas/prints/", "windows": None},
    }


def test_infer_prefix_map_windows() -> None:
    """Windows prefix (backslash) assigns os_key=windows for all libraries."""
    result = infer_prefix_map("C:\\prints\\", [1, 3])
    assert result == {
        "1": {"windows": "C:\\prints\\", "posix": None},
        "3": {"windows": "C:\\prints\\", "posix": None},
    }


def test_infer_prefix_map_empty_library_list() -> None:
    """Returns empty dict when there are no libraries."""
    result = infer_prefix_map("/mnt/nas/", [])
    assert result == {}


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_path_prefixes_empty_for_new_user(client: AsyncClient) -> None:
    """Fresh user has an empty path_prefixes map."""
    await _admin_setup(client)
    resp = await client.get("/api/me/path-prefixes")
    assert resp.status_code == 200
    data = resp.json()
    assert "path_prefixes" in data
    assert data["path_prefixes"] == {}


@pytest.mark.asyncio
async def test_put_get_path_prefixes_round_trip(client: AsyncClient) -> None:
    """PUT then GET correctly round-trips the prefix map."""
    csrf = await _admin_setup(client)
    lib_id = await _create_library(client, csrf)

    put_body = {
        "path_prefixes": {
            str(lib_id): {"posix": "/mnt/nas/prints/", "windows": None}
        }
    }
    put_resp = await client.put(
        "/api/me/path-prefixes",
        json=put_body,
        headers={"X-CSRF-Token": csrf},
    )
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["path_prefixes"][str(lib_id)]["posix"] == "/mnt/nas/prints/"
    assert put_data["path_prefixes"][str(lib_id)]["windows"] is None

    # Verify GET returns the same data.
    get_resp = await client.get("/api/me/path-prefixes")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["path_prefixes"][str(lib_id)]["posix"] == "/mnt/nas/prints/"
    assert get_data["path_prefixes"][str(lib_id)]["windows"] is None


@pytest.mark.asyncio
async def test_put_path_prefixes_both_os(client: AsyncClient) -> None:
    """Both OS entries can be set for the same library."""
    csrf = await _admin_setup(client)
    lib_id = await _create_library(client, csrf)

    resp = await client.put(
        "/api/me/path-prefixes",
        json={
            "path_prefixes": {
                str(lib_id): {
                    "posix": "/mnt/nas/",
                    "windows": "Z:\\3dprints\\",
                }
            }
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    entry = resp.json()["path_prefixes"][str(lib_id)]
    assert entry["posix"] == "/mnt/nas/"
    assert entry["windows"] == "Z:\\3dprints\\"


@pytest.mark.asyncio
async def test_put_path_prefixes_unknown_library_ignored(client: AsyncClient) -> None:
    """Unknown library IDs in the PUT body are silently ignored."""
    csrf = await _admin_setup(client)
    lib_id = await _create_library(client, csrf)
    fake_id = 99999

    resp = await client.put(
        "/api/me/path-prefixes",
        json={
            "path_prefixes": {
                str(lib_id): {"posix": "/mnt/nas/", "windows": None},
                str(fake_id): {"posix": "/mnt/fake/", "windows": None},
            }
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    result = resp.json()["path_prefixes"]
    assert str(lib_id) in result
    assert str(fake_id) not in result


@pytest.mark.asyncio
async def test_put_path_prefixes_empty_clears_map(client: AsyncClient) -> None:
    """PUT with empty path_prefixes clears all stored prefixes."""
    csrf = await _admin_setup(client)
    lib_id = await _create_library(client, csrf)

    # First set something.
    await client.put(
        "/api/me/path-prefixes",
        json={"path_prefixes": {str(lib_id): {"posix": "/mnt/nas/", "windows": None}}},
        headers={"X-CSRF-Token": csrf},
    )

    # Now clear with empty map.
    resp = await client.put(
        "/api/me/path-prefixes",
        json={"path_prefixes": {}},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["path_prefixes"] == {}

    get_resp = await client.get("/api/me/path-prefixes")
    assert get_resp.json()["path_prefixes"] == {}


@pytest.mark.asyncio
async def test_get_path_prefixes_requires_auth(client: AsyncClient) -> None:
    """GET /api/me/path-prefixes requires authentication."""
    resp = await client.get("/api/me/path-prefixes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_put_path_prefixes_requires_csrf(client: AsyncClient) -> None:
    """PUT /api/me/path-prefixes requires CSRF token."""
    await _admin_setup(client)
    resp = await client.put(
        "/api/me/path-prefixes",
        json={"path_prefixes": {}},
        # No X-CSRF-Token header
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_migration_data_logic_via_db(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Simulate migration 0017: a user with legacy path_prefix gets a path_prefixes map.

    Exercises infer_prefix_map (same logic as the Alembic data migration) by
    writing the result to the DB via raw SQL, then reading it back through the API.
    """
    csrf = await _admin_setup(client)
    lib_id = await _create_library(client, csrf)

    # Get the admin user's id.
    me_resp = await client.get("/api/auth/me")
    user_id = me_resp.json()["user_id"]

    # Simulate pre-migration state: legacy path_prefix set, path_prefixes null.
    legacy_prefix = "/mnt/nas/3dprints/"
    db_user_result = await db_session.execute(select(User).where(User.id == user_id))
    db_user = db_user_result.scalar_one()
    db_user.path_prefix = legacy_prefix
    db_user.path_prefixes = None
    await db_session.flush()

    # Apply the same migration helper to produce the map, then write it.
    migrated_map = infer_prefix_map(legacy_prefix, [lib_id])
    db_user.path_prefixes = migrated_map
    await db_session.flush()

    # Verify via API: the legacy posix prefix is now in the per-library map.
    resp = await client.get("/api/me/path-prefixes")
    assert resp.status_code == 200
    prefixes = resp.json()["path_prefixes"]
    assert str(lib_id) in prefixes
    assert prefixes[str(lib_id)]["posix"] == legacy_prefix
    assert prefixes[str(lib_id)]["windows"] is None
