"""Tests for user management and admin-only authorization."""

import pytest
from httpx import AsyncClient


async def _admin_setup(client: AsyncClient) -> str:
    """Setup admin and return CSRF token."""
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
async def test_list_users_admin(client: AsyncClient) -> None:
    """Admin can list all users."""
    await _admin_setup(client)
    resp = await client.get("/api/users")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    assert users[0]["email"] == "admin@example.com"
    assert users[0]["role"] == "admin"


@pytest.mark.asyncio
async def test_create_user_admin(client: AsyncClient) -> None:
    """Admin can create a new user directly."""
    csrf = await _admin_setup(client)
    resp = await client.post(
        "/api/users",
        json={
            "email": "newuser@example.com",
            "name": "New User",
            "password": "password123",
            "role": "user",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@example.com"
    assert data["role"] == "user"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_disable_user(client: AsyncClient) -> None:
    """Admin can disable a user (is_active = False)."""
    csrf = await _admin_setup(client)
    # Create user
    create_resp = await client.post(
        "/api/users",
        json={
            "email": "user@example.com",
            "name": "User",
            "password": "password123",
        },
        headers={"X-CSRF-Token": csrf},
    )
    user_id = create_resp.json()["id"]

    # Disable
    patch_resp = await client.patch(
        f"/api/users/{user_id}",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_disabled_user_cannot_login(client: AsyncClient) -> None:
    """Disabled user cannot login."""
    csrf = await _admin_setup(client)
    create_resp = await client.post(
        "/api/users",
        json={
            "email": "user@example.com",
            "name": "User",
            "password": "password123",
        },
        headers={"X-CSRF-Token": csrf},
    )
    user_id = create_resp.json()["id"]
    await client.patch(
        f"/api/users/{user_id}",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf},
    )

    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert login_resp.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_cannot_list_users(client: AsyncClient) -> None:
    """Standard user gets 403 on GET /api/users."""
    csrf = await _admin_setup(client)

    # Create standard user via direct endpoint
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

    # Login as standard user
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )

    resp = await client.get("/api/users")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_create_user(client: AsyncClient) -> None:
    """Standard user gets 403 on POST /api/users."""
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
    user_csrf = client.cookies.get("pf3d_csrf", "")

    resp = await client.post(
        "/api/users",
        json={"email": "another@example.com", "name": "Another", "password": "pw123456"},
        headers={"X-CSRF-Token": user_csrf},
    )
    assert resp.status_code == 403
