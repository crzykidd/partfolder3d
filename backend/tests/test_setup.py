"""Tests for first-run setup: create admin + lock."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_setup_status_returns_not_initialized(client: AsyncClient) -> None:
    """Fresh instance: GET /api/setup/status → { initialized: false }."""
    resp = await client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json() == {"initialized": False}


@pytest.mark.asyncio
async def test_setup_creates_admin(client: AsyncClient) -> None:
    """POST /api/setup creates the admin and returns 201."""
    resp = await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
            "instance_name": "My PartFolder",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ok"] is True
    assert "user_id" in data


@pytest.mark.asyncio
async def test_setup_locks_after_first_run(client: AsyncClient) -> None:
    """Second POST /api/setup returns 409 Conflict."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    resp = await client.post(
        "/api/setup",
        json={
            "admin_email": "admin2@example.com",
            "admin_name": "Admin2",
            "admin_password": "securepassword2",
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_setup_status_after_init(client: AsyncClient) -> None:
    """After setup, GET /api/setup/status → { initialized: true }."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    resp = await client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json()["initialized"] is True


@pytest.mark.asyncio
async def test_setup_rejects_short_password(client: AsyncClient) -> None:
    """Short password is rejected with 422."""
    resp = await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "short",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_setup_sets_session_cookie(client: AsyncClient) -> None:
    """POST /api/setup sets the session cookie on the response."""
    resp = await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    assert resp.status_code == 201
    assert "pf3d_session" in resp.cookies


@pytest.mark.asyncio
async def test_setup_autologin_session_immediately_accessible(
    client: AsyncClient,
) -> None:
    """POST /api/setup returns a session cookie that is immediately usable.

    Regression guard for issue #13: the auto-login session must be committed
    to the DB before the 201 response is returned, so a follow-up
    GET /api/auth/me with the returned cookie succeeds (200) rather than 401.
    """
    setup_resp = await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    assert setup_resp.status_code == 201
    assert "pf3d_session" in setup_resp.cookies

    # httpx's AsyncClient preserves cookies between requests in the same
    # instance, so this /me request goes out with the pf3d_session cookie
    # that was just set — simulating what a browser does immediately after
    # the setup POST resolves.
    me_resp = await client.get("/api/auth/me")
    assert me_resp.status_code == 200, (
        f"Expected 200 from /me immediately after setup (session not committed?), "
        f"got {me_resp.status_code}: {me_resp.text}"
    )
