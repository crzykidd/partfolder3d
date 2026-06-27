"""Tests for instance settings and per-user theme persistence."""

import pytest
from httpx import AsyncClient


async def _admin_setup(client: AsyncClient) -> str:
    """Setup admin, return CSRF token."""
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


@pytest.mark.asyncio
async def test_list_settings_admin(client: AsyncClient) -> None:
    """Admin can list instance settings."""
    await _admin_setup(client)
    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    # Setup created some instance.* settings
    settings = resp.json()
    keys = {s["key"] for s in settings}
    assert "instance.name" in keys


@pytest.mark.asyncio
async def test_upsert_setting(client: AsyncClient) -> None:
    """Admin can create and update settings."""
    csrf = await _admin_setup(client)

    # Create
    resp = await client.put(
        "/api/settings/scan.auto_mode",
        json={"value": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] is True

    # Update
    resp2 = await client.put(
        "/api/settings/scan.auto_mode",
        json={"value": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp2.status_code == 200
    assert resp2.json()["value"] is False


@pytest.mark.asyncio
async def test_non_admin_cannot_list_settings(client: AsyncClient) -> None:
    """Standard user gets 403 on GET /api/settings."""
    csrf = await _admin_setup(client)

    await client.post(
        "/api/users",
        json={
            "email": "user@example.com",
            "name": "User",
            "password": "password123",
            "role": "user",
        },
        headers={"X-CSRF-Token": csrf},
    )
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )

    resp = await client.get("/api/settings")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_theme(client: AsyncClient) -> None:
    """GET /api/me/theme returns default system theme."""
    await _admin_setup(client)
    resp = await client.get("/api/me/theme")
    assert resp.status_code == 200
    assert resp.json()["theme_pref"] == "system"


@pytest.mark.asyncio
async def test_update_theme(client: AsyncClient) -> None:
    """PUT /api/me/theme persists the theme preference."""
    csrf = await _admin_setup(client)

    resp = await client.put(
        "/api/me/theme",
        json={"theme_pref": "dark"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["theme_pref"] == "dark"

    # Verify it persisted
    get_resp = await client.get("/api/me/theme")
    assert get_resp.json()["theme_pref"] == "dark"


@pytest.mark.asyncio
async def test_invalid_theme_rejected(client: AsyncClient) -> None:
    """Invalid theme value returns 422."""
    csrf = await _admin_setup(client)

    resp = await client.put(
        "/api/me/theme",
        json={"theme_pref": "rainbow"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_theme_requires_auth(client: AsyncClient) -> None:
    """GET/PUT /api/me/theme requires authentication."""
    resp = await client.get("/api/me/theme")
    assert resp.status_code == 401
