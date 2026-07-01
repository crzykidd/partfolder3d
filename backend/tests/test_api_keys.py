"""Tests for per-user API key management."""

import pytest
from httpx import AsyncClient


async def _admin_setup(client: AsyncClient) -> str:
    """Setup admin and return CSRF token."""
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
async def test_create_api_key(client: AsyncClient) -> None:
    """Creating an API key returns the raw key once."""
    csrf = await _admin_setup(client)
    resp = await client.post(
        "/api/api-keys",
        json={"label": "my-key"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["label"] == "my-key"
    assert "key" in data
    assert len(data["key"]) > 20  # high entropy key


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient) -> None:
    """Listing keys does NOT return the raw key value."""
    csrf = await _admin_setup(client)
    await client.post(
        "/api/api-keys",
        json={"label": "key-1"},
        headers={"X-CSRF-Token": csrf},
    )
    resp = await client.get("/api/api-keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) == 1
    assert keys[0]["label"] == "key-1"
    assert "key" not in keys[0]  # raw key never re-exposed


@pytest.mark.asyncio
async def test_api_key_authenticates(client: AsyncClient) -> None:
    """Bearer <key> authenticates and resolves to the correct user."""
    csrf = await _admin_setup(client)
    key_resp = await client.post(
        "/api/api-keys",
        json={"label": "bearer-test"},
        headers={"X-CSRF-Token": csrf},
    )
    raw_key = key_resp.json()["key"]

    # Logout cookie session
    await client.post("/api/auth/logout")

    # Authenticate with Bearer token
    me_resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "admin@example.com"


@pytest.mark.asyncio
async def test_revoke_api_key(client: AsyncClient) -> None:
    """Revoking a key makes it unusable."""
    csrf = await _admin_setup(client)
    key_resp = await client.post(
        "/api/api-keys",
        json={"label": "revoke-me"},
        headers={"X-CSRF-Token": csrf},
    )
    key_data = key_resp.json()
    raw_key = key_data["key"]
    key_id = key_data["id"]

    # Revoke
    del_resp = await client.delete(
        f"/api/api-keys/{key_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204

    # Key should now fail auth
    await client.post("/api/auth/logout")
    me_resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert me_resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_bearer_token(client: AsyncClient) -> None:
    """A nonexistent Bearer token returns 401."""
    await _admin_setup(client)
    await client.post("/api/auth/logout")
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer totally-invalid-key-value"},
    )
    assert resp.status_code == 401
