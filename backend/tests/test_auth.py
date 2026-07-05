"""Tests for login/logout/me and CSRF protection."""

from typing import Any

import pytest
from httpx import AsyncClient


async def _setup_and_login(client: AsyncClient) -> dict:
    """Helper: run setup, return login response data."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin User",
            "admin_password": "securepassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "securepassword1"},
    )
    return resp


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    """Valid credentials return 200 and set session cookie."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "securepassword1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["email"] == "admin@example.com"
    assert data["role"] == "admin"
    assert "pf3d_session" in resp.cookies


@pytest.mark.asyncio
async def test_login_bad_password(client: AsyncClient) -> None:
    """Wrong password returns 401."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient) -> None:
    """Unknown email returns 401."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "securepassword1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_runs_dummy_verify(
    client: AsyncClient, monkeypatch: Any
) -> None:
    """Unknown-email login still runs a password verify (no timing oracle).

    The authenticate() path must NOT short-circuit before hashing when the email
    is missing, otherwise response time leaks account existence. We spy on
    verify_password and assert it is invoked once against the fixed dummy hash.
    """
    import app.auth.provider as provider_mod

    calls: list[str] = []
    real_verify = provider_mod.verify_password

    def spy(password: str, hashed: str) -> bool:
        calls.append(hashed)
        return real_verify(password, hashed)

    monkeypatch.setattr(provider_mod, "verify_password", spy)

    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )

    resp = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "whatever12"},
    )
    assert resp.status_code == 401
    # verify ran exactly once, against the dummy hash (not short-circuited).
    assert calls == [provider_mod._DUMMY_PASSWORD_HASH]


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient) -> None:
    """GET /api/auth/me returns user info when session cookie is set."""
    login_resp = await _setup_and_login(client)
    assert login_resp.status_code == 200
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "admin@example.com"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient) -> None:
    """GET /api/auth/me returns 401 without a session."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_session(client: AsyncClient) -> None:
    """POST /api/auth/logout invalidates the session; subsequent /me returns 401."""
    await _setup_and_login(client)
    # Verify logged in
    assert (await client.get("/api/auth/me")).status_code == 200
    # Logout
    logout_resp = await client.post("/api/auth/logout")
    assert logout_resp.status_code == 200
    # Session cookie is cleared (cookie jar is empty or has empty value)
    # Now /me should return 401
    me_resp = await client.get("/api/auth/me")
    assert me_resp.status_code == 401


@pytest.mark.asyncio
async def test_csrf_required_for_state_change(client: AsyncClient) -> None:
    """State-changing requests without X-CSRF-Token header return 403."""
    await _setup_and_login(client)
    # Try to create a user without CSRF token (no header)
    resp = await client.post(
        "/api/users",
        json={
            "email": "newuser@example.com",
            "name": "New User",
            "password": "password123",
        },
        # No X-CSRF-Token header
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_csrf_valid_token_allows_state_change(client: AsyncClient) -> None:
    """State-changing requests WITH X-CSRF-Token header succeed."""
    await _setup_and_login(client)
    csrf_token = client.cookies.get("pf3d_csrf")
    assert csrf_token is not None

    resp = await client.post(
        "/api/users",
        json={
            "email": "newuser@example.com",
            "name": "New User",
            "password": "password123",
            "role": "user",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_csrf_exempted_for_bearer(client: AsyncClient) -> None:
    """Bearer-authenticated requests don't need CSRF token."""
    # Setup and login, create an API key
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
    csrf_token = client.cookies.get("pf3d_csrf")
    key_resp = await client.post(
        "/api/api-keys",
        json={"label": "test-key"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert key_resp.status_code == 201
    raw_key = key_resp.json()["key"]

    # Now logout (clear cookie)
    await client.post("/api/auth/logout")

    # Use Bearer token without CSRF header — should reach /api/auth/me fine
    me_resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "admin@example.com"
