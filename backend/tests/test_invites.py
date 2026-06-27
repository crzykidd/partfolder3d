"""Tests for invite create→accept flow and revocation."""

import pytest
from httpx import AsyncClient


async def _admin_setup(client: AsyncClient) -> str:
    """Setup admin, return CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "securepassword1"},
    )
    return client.cookies.get("pf3d_csrf", "")


@pytest.mark.asyncio
async def test_create_invite(client: AsyncClient) -> None:
    """Admin can create an invite link with a raw token."""
    csrf = await _admin_setup(client)
    resp = await client.post(
        "/api/invites",
        json={"email": "newuser@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@example.com"
    assert data["status"] == "pending"
    assert "token" in data
    assert data["token"] is not None


@pytest.mark.asyncio
async def test_accept_invite(client: AsyncClient) -> None:
    """User can accept invite by providing name + password."""
    csrf = await _admin_setup(client)
    invite_resp = await client.post(
        "/api/invites",
        json={"email": "newuser@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    token = invite_resp.json()["token"]

    accept_resp = await client.post(
        f"/api/invites/{token}/accept",
        json={"name": "New User", "password": "newpassword1"},
    )
    assert accept_resp.status_code == 201
    assert accept_resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_accepted_user_can_login(client: AsyncClient) -> None:
    """Accepted invite user can log in with their credentials."""
    csrf = await _admin_setup(client)
    invite_resp = await client.post(
        "/api/invites",
        json={"email": "newuser@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    token = invite_resp.json()["token"]

    await client.post(
        f"/api/invites/{token}/accept",
        json={"name": "New User", "password": "newpassword1"},
    )

    # Logout admin
    await client.post("/api/auth/logout")

    # Login as new user
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "newuser@example.com", "password": "newpassword1"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["role"] == "user"


@pytest.mark.asyncio
async def test_invite_accept_twice_fails(client: AsyncClient) -> None:
    """Accepting an invite twice returns 409."""
    csrf = await _admin_setup(client)
    invite_resp = await client.post(
        "/api/invites",
        json={"email": "newuser@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    token = invite_resp.json()["token"]

    await client.post(
        f"/api/invites/{token}/accept",
        json={"name": "New User", "password": "newpassword1"},
    )
    # Second accept
    resp2 = await client.post(
        f"/api/invites/{token}/accept",
        json={"name": "New User2", "password": "newpassword2"},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_revoke_invite(client: AsyncClient) -> None:
    """Revoking an invite prevents acceptance."""
    csrf = await _admin_setup(client)
    invite_resp = await client.post(
        "/api/invites",
        json={"email": "newuser@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    invite_id = invite_resp.json()["id"]
    token = invite_resp.json()["token"]

    # Revoke
    del_resp = await client.delete(
        f"/api/invites/{invite_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204

    # Try to accept
    accept_resp = await client.post(
        f"/api/invites/{token}/accept",
        json={"name": "New User", "password": "newpassword1"},
    )
    assert accept_resp.status_code == 409


@pytest.mark.asyncio
async def test_list_invites(client: AsyncClient) -> None:
    """Admin can list invites with their status."""
    csrf = await _admin_setup(client)
    await client.post(
        "/api/invites",
        json={"email": "user1@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    await client.post(
        "/api/invites",
        json={"email": "user2@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    resp = await client.get("/api/invites")
    assert resp.status_code == 200
    invites = resp.json()
    assert len(invites) == 2
    emails = {inv["email"] for inv in invites}
    assert emails == {"user1@example.com", "user2@example.com"}


@pytest.mark.asyncio
async def test_non_admin_cannot_create_invite(client: AsyncClient) -> None:
    """Standard user cannot create invites (403)."""
    csrf = await _admin_setup(client)

    # Create a second user
    await client.post(
        "/api/invites",
        json={"email": "user@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    invite_token = (
        await client.post(
            "/api/invites",
            json={"email": "user@example.com"},
            headers={"X-CSRF-Token": csrf},
        )
    ).json()["token"]

    await client.post(
        f"/api/invites/{invite_token}/accept",
        json={"name": "Standard User", "password": "password123"},
    )

    # Login as standard user
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    user_csrf = client.cookies.get("pf3d_csrf", "")

    # Try to create an invite as standard user
    resp = await client.post(
        "/api/invites",
        json={"email": "another@example.com"},
        headers={"X-CSRF-Token": user_csrf},
    )
    assert resp.status_code == 403
