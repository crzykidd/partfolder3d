"""Tests for per-user nav_layout preference (Phase 11).

Tests cover:
  - GET /api/me/nav-layout: default resolved by role (admin→side, user→top)
  - PUT /api/me/nav-layout: persists preference
  - PUT /api/me/nav-layout with null: resets to role default
  - Invalid value rejected (422)
  - Auth required (401)
"""

import pytest
from httpx import AsyncClient


async def _admin_setup(client: AsyncClient) -> str:
    """Create admin, login, return CSRF token."""
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


async def _create_user(client: AsyncClient, csrf: str, email: str = "user@example.com") -> None:
    """Create a regular user via admin endpoint."""
    await client.post(
        "/api/users",
        json={
            "email": email,
            "name": "Regular User",
            "password": "password123",
            "role": "user",
        },
        headers={"X-CSRF-Token": csrf},
    )


@pytest.mark.asyncio
async def test_admin_default_layout_is_side(client: AsyncClient) -> None:
    """Admin with no explicit preference gets 'side' as default."""
    await _admin_setup(client)
    resp = await client.get("/api/me/nav-layout")
    assert resp.status_code == 200
    assert resp.json()["nav_layout"] == "side"


@pytest.mark.asyncio
async def test_user_default_layout_is_top(client: AsyncClient) -> None:
    """Regular user with no explicit preference gets 'top' as default."""
    csrf = await _admin_setup(client)
    await _create_user(client, csrf)

    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )

    resp = await client.get("/api/me/nav-layout")
    assert resp.status_code == 200
    assert resp.json()["nav_layout"] == "top"


@pytest.mark.asyncio
async def test_set_nav_layout(client: AsyncClient) -> None:
    """PUT /api/me/nav-layout persists the preference."""
    csrf = await _admin_setup(client)

    # Admin sets layout to 'top' (overriding role default)
    resp = await client.put(
        "/api/me/nav-layout",
        json={"nav_layout": "top"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["nav_layout"] == "top"

    # Verify it persisted
    get_resp = await client.get("/api/me/nav-layout")
    assert get_resp.json()["nav_layout"] == "top"


@pytest.mark.asyncio
async def test_reset_nav_layout_to_role_default(client: AsyncClient) -> None:
    """PUT with nav_layout=null resets to role default."""
    csrf = await _admin_setup(client)

    # First override
    await client.put(
        "/api/me/nav-layout",
        json={"nav_layout": "top"},
        headers={"X-CSRF-Token": csrf},
    )
    # Then reset
    resp = await client.put(
        "/api/me/nav-layout",
        json={"nav_layout": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    # admin default is 'side'
    assert resp.json()["nav_layout"] == "side"


@pytest.mark.asyncio
async def test_invalid_layout_rejected(client: AsyncClient) -> None:
    """Invalid nav_layout value returns 422."""
    csrf = await _admin_setup(client)
    resp = await client.put(
        "/api/me/nav-layout",
        json={"nav_layout": "left"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_nav_layout_requires_auth(client: AsyncClient) -> None:
    """GET/PUT /api/me/nav-layout requires authentication."""
    resp = await client.get("/api/me/nav-layout")
    assert resp.status_code == 401
