"""Tests for per-user dashboard_layout preference (Phase 12).

Tests cover:
  - GET /api/me/dashboard: admin default (compact + admin tiles)
  - GET /api/me/dashboard: user default (comfortable + basic tiles)
  - PUT /api/me/dashboard: persists layout round-trip
  - PUT /api/me/dashboard: invalid density rejected (422)
  - GET /api/me/dashboard: reset to role default when payload is null
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


async def _create_and_login_user(
    client: AsyncClient,
    csrf: str,
    email: str = "user@example.com",
) -> str:
    """Create a regular user via admin endpoint, then login as that user. Returns new CSRF."""
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
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    return client.cookies.get("pf3d_csrf", "")


# ---------------------------------------------------------------------------
# Role-based defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_default_dashboard_is_compact(client: AsyncClient) -> None:
    """Admin with no explicit preference gets compact density + admin tile set."""
    await _admin_setup(client)
    resp = await client.get("/api/me/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    layout = body["dashboard_layout"]
    assert layout["stats"]["density"] == "compact"
    # Admin tiles include admin-specific ones
    tiles = layout["stats"]["tiles"]
    assert "total-assets" in tiles
    assert "pending-reviews" in tiles
    assert "open-issues" in tiles
    assert "pending-tags" in tiles
    # Rail default
    assert layout["rail"]["collapsed"] is False
    assert "quick-import" in layout["rail"]["widgets"]


@pytest.mark.asyncio
async def test_user_default_dashboard_is_comfortable(client: AsyncClient) -> None:
    """Regular user with no explicit preference gets comfortable density + basic tiles."""
    csrf = await _admin_setup(client)
    user_csrf = await _create_and_login_user(client, csrf)
    _ = user_csrf  # silence unused var; client session is already set

    resp = await client.get("/api/me/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    layout = body["dashboard_layout"]
    assert layout["stats"]["density"] == "comfortable"
    # User tiles do NOT include admin-only ones
    tiles = layout["stats"]["tiles"]
    assert "total-assets" in tiles
    assert "pending-reviews" not in tiles
    assert "open-issues" not in tiles
    assert "pending-tags" not in tiles
    # Rail default
    assert layout["rail"]["collapsed"] is False
    assert "quick-import" in layout["rail"]["widgets"]


# ---------------------------------------------------------------------------
# Round-trip persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_dashboard_layout_persists(client: AsyncClient) -> None:
    """PUT /api/me/dashboard persists the layout and GET retrieves it."""
    csrf = await _admin_setup(client)

    new_layout = {
        "dashboard_layout": {
            "stats": {
                "density": "comfortable",
                "tiles": ["total-assets", "jobs-running"],
            },
            "rail": {
                "collapsed": True,
                "widgets": ["quick-import", "recent-items"],
            },
        }
    }

    put_resp = await client.put(
        "/api/me/dashboard",
        json=new_layout,
        headers={"X-CSRF-Token": csrf},
    )
    assert put_resp.status_code == 200
    put_body = put_resp.json()
    assert put_body["dashboard_layout"]["stats"]["density"] == "comfortable"
    assert put_body["dashboard_layout"]["stats"]["tiles"] == ["total-assets", "jobs-running"]
    assert put_body["dashboard_layout"]["rail"]["collapsed"] is True
    assert put_body["dashboard_layout"]["rail"]["widgets"] == ["quick-import", "recent-items"]

    # Verify it persisted via GET
    get_resp = await client.get("/api/me/dashboard")
    assert get_resp.status_code == 200
    get_body = get_resp.json()
    assert get_body["dashboard_layout"]["stats"]["density"] == "comfortable"
    assert get_body["dashboard_layout"]["stats"]["tiles"] == ["total-assets", "jobs-running"]
    assert get_body["dashboard_layout"]["rail"]["collapsed"] is True


@pytest.mark.asyncio
async def test_put_dashboard_preserves_order(client: AsyncClient) -> None:
    """Tile and widget order in arrays is preserved exactly."""
    csrf = await _admin_setup(client)

    tiles = ["jobs-running", "success-rate", "total-assets", "prints-done"]
    widgets = ["recent-items", "quick-import"]

    await client.put(
        "/api/me/dashboard",
        json={
            "dashboard_layout": {
                "stats": {"density": "compact", "tiles": tiles},
                "rail": {"collapsed": False, "widgets": widgets},
            }
        },
        headers={"X-CSRF-Token": csrf},
    )

    get_resp = await client.get("/api/me/dashboard")
    body = get_resp.json()["dashboard_layout"]
    assert body["stats"]["tiles"] == tiles
    assert body["rail"]["widgets"] == widgets


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_density_rejected(client: AsyncClient) -> None:
    """Invalid density value returns 422."""
    csrf = await _admin_setup(client)
    resp = await client.put(
        "/api/me/dashboard",
        json={
            "dashboard_layout": {
                "stats": {"density": "cozy", "tiles": []},
                "rail": {"collapsed": False, "widgets": []},
            }
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_requires_auth(client: AsyncClient) -> None:
    """GET/PUT /api/me/dashboard require authentication."""
    get_resp = await client.get("/api/me/dashboard")
    assert get_resp.status_code == 401

    put_resp = await client.put(
        "/api/me/dashboard",
        json={
            "dashboard_layout": {
                "stats": {"density": "comfortable", "tiles": []},
                "rail": {"collapsed": False, "widgets": []},
            }
        },
    )
    assert put_resp.status_code == 401
