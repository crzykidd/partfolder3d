"""Tests for admin-generated password reset links."""

import pytest
from httpx import AsyncClient


async def _setup_with_user(client: AsyncClient) -> tuple[str, str]:
    """Setup admin + invite a user. Returns (admin_csrf, user_email)."""
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
    csrf = client.cookies.get("pf3d_csrf", "")

    # Create a user via invite
    invite_resp = await client.post(
        "/api/invites",
        json={"email": "user@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    token = invite_resp.json()["token"]
    await client.post(
        f"/api/invites/{token}/accept",
        json={"name": "Regular User", "password": "oldpassword1"},
    )
    return csrf, "user@example.com"


@pytest.mark.asyncio
async def test_create_reset_token(client: AsyncClient) -> None:
    """Admin can create a reset token for a user."""
    csrf, user_email = await _setup_with_user(client)

    resp = await client.post(
        "/api/password-reset",
        json={"email": user_email},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert data["token"] is not None
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_use_reset_token(client: AsyncClient) -> None:
    """User can set a new password via the reset token."""
    csrf, user_email = await _setup_with_user(client)

    reset_resp = await client.post(
        "/api/password-reset",
        json={"email": user_email},
        headers={"X-CSRF-Token": csrf},
    )
    token = reset_resp.json()["token"]

    use_resp = await client.post(
        f"/api/password-reset/{token}",
        json={"new_password": "newpassword123"},
    )
    assert use_resp.status_code == 200
    assert use_resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_new_password_works(client: AsyncClient) -> None:
    """After reset, user can login with the new password."""
    csrf, user_email = await _setup_with_user(client)

    reset_resp = await client.post(
        "/api/password-reset",
        json={"email": user_email},
        headers={"X-CSRF-Token": csrf},
    )
    token = reset_resp.json()["token"]
    await client.post(
        f"/api/password-reset/{token}",
        json={"new_password": "newpassword123"},
    )

    # Logout admin
    await client.post("/api/auth/logout")

    # Old password should fail
    old_login = await client.post(
        "/api/auth/login",
        json={"email": user_email, "password": "oldpassword1"},
    )
    assert old_login.status_code == 401

    # New password should work
    new_login = await client.post(
        "/api/auth/login",
        json={"email": user_email, "password": "newpassword123"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_reset_invalidates_existing_sessions(client: AsyncClient) -> None:
    """Consuming a reset token deactivates the user's existing sessions."""
    csrf, user_email = await _setup_with_user(client)

    # Admin mints a reset token while still logged in as admin.
    reset_resp = await client.post(
        "/api/password-reset",
        json={"email": user_email},
        headers={"X-CSRF-Token": csrf},
    )
    assert reset_resp.status_code == 201
    token = reset_resp.json()["token"]

    # The user logs in, establishing a session in the shared cookie jar.
    login = await client.post(
        "/api/auth/login",
        json={"email": user_email, "password": "oldpassword1"},
    )
    assert login.status_code == 200
    me_before = await client.get("/api/auth/me")
    assert me_before.status_code == 200
    assert me_before.json()["email"] == user_email

    # Consume the reset token (public endpoint) — sets a new password.
    use = await client.post(
        f"/api/password-reset/{token}",
        json={"new_password": "brandnewpass1"},
    )
    assert use.status_code == 200

    # The previously issued session cookie is now rejected (session killed).
    me_after = await client.get("/api/auth/me")
    assert me_after.status_code == 401


@pytest.mark.asyncio
async def test_reset_token_single_use(client: AsyncClient) -> None:
    """A reset token can only be used once."""
    csrf, user_email = await _setup_with_user(client)

    reset_resp = await client.post(
        "/api/password-reset",
        json={"email": user_email},
        headers={"X-CSRF-Token": csrf},
    )
    token = reset_resp.json()["token"]
    await client.post(
        f"/api/password-reset/{token}",
        json={"new_password": "newpassword123"},
    )
    # Use again
    resp2 = await client.post(
        f"/api/password-reset/{token}",
        json={"new_password": "anotherpassword"},
    )
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_revoke_reset_token(client: AsyncClient) -> None:
    """Admin can revoke a reset token."""
    csrf, user_email = await _setup_with_user(client)

    reset_resp = await client.post(
        "/api/password-reset",
        json={"email": user_email},
        headers={"X-CSRF-Token": csrf},
    )
    reset_data = reset_resp.json()
    token = reset_data["token"]
    reset_id = reset_data["id"]

    # Revoke
    del_resp = await client.delete(
        f"/api/password-reset/{reset_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204

    # Token is now unusable
    use_resp = await client.post(
        f"/api/password-reset/{token}",
        json={"new_password": "newpassword123"},
    )
    assert use_resp.status_code == 404


@pytest.mark.asyncio
async def test_reset_unknown_email(client: AsyncClient) -> None:
    """Reset for unknown email returns 404."""
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
    csrf = client.cookies.get("pf3d_csrf", "")

    resp = await client.post(
        "/api/password-reset",
        json={"email": "nobody@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404
