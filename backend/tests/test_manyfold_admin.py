"""Manyfold connector — Part 1: config + admin API tests.

Mirrors test_flaresolverr.py's pattern: _setup_and_login, admin CRUD via the
HTTP client, and monkeypatching the storage-layer seam for the
test-connection endpoint (no real network calls).

Covers:
  - create; list/get never leak the secret (has_secret True, no secret field)
  - duplicate-domain 409
  - base_url normalization (trailing slash, host lowercasing) + invalid scheme 422
  - PATCH rotates secret + toggles enabled + re-derives domain
  - DELETE
  - test-connection success and failure (401 / 403 / connection error / no secret)
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> str:
    """Initialize instance and log in as admin; returns CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@test.com",
            "admin_name": "Admin",
            "admin_password": "adminpassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "adminpassword1"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


async def _create_instance(
    client: AsyncClient,
    csrf: str,
    *,
    base_url: str = "https://manyfold.crzynet.com",
    client_id: str = "test-client-id",
    client_secret: str = "s3cr3t-value",
    display_name: str | None = "My Manyfold",
    scopes: str | None = None,
    enabled: bool = True,
) -> Any:
    body: dict[str, Any] = {
        "base_url": base_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "display_name": display_name,
        "enabled": enabled,
    }
    if scopes is not None:
        body["scopes"] = scopes
    return await client.post(
        "/api/admin/manyfold",
        json=body,
        headers={"X-CSRF-Token": csrf},
    )


# ---------------------------------------------------------------------------
# Create / list / get — secret never leaked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_manyfold_instance(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    resp = await _create_instance(client, csrf)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["base_url"] == "https://manyfold.crzynet.com"
    assert data["domain"] == "manyfold.crzynet.com"
    assert data["client_id"] == "test-client-id"
    assert data["has_secret"] is True
    assert data["scopes"] == "public read"
    assert data["enabled"] is True
    assert data["last_connected_at"] is None
    assert "client_secret" not in data


@pytest.mark.asyncio
async def test_list_never_leaks_secret(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    await _create_instance(client, csrf)

    resp = await client.get("/api/admin/manyfold")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["has_secret"] is True
    assert "client_secret" not in data[0]
    assert "client_secret_enc" not in data[0]


@pytest.mark.asyncio
async def test_get_never_leaks_secret(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    create_resp = await _create_instance(client, csrf)
    instance_id = create_resp.json()["id"]

    resp = await client.get(f"/api/admin/manyfold/{instance_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_secret"] is True
    assert "client_secret" not in data


@pytest.mark.asyncio
async def test_get_missing_instance_404(client: AsyncClient) -> None:
    await _setup_and_login(client)
    resp = await client.get("/api/admin/manyfold/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# base_url normalization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_url_normalized_trailing_slash_and_case(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    resp = await _create_instance(
        client, csrf, base_url="HTTPS://Manyfold.CrzyNet.com/"
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["base_url"] == "https://manyfold.crzynet.com"
    assert data["domain"] == "manyfold.crzynet.com"


@pytest.mark.asyncio
async def test_invalid_base_url_scheme_rejected(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    resp = await _create_instance(client, csrf, base_url="ftp://manyfold.example.com")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_empty_base_url_rejected(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    resp = await _create_instance(client, csrf, base_url="   ")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Duplicate domain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_domain_returns_409(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    resp1 = await _create_instance(client, csrf, base_url="https://manyfold.example.com")
    assert resp1.status_code == 201

    # Same host, different path/scheme casing — still the same domain.
    resp2 = await _create_instance(
        client, csrf, base_url="https://Manyfold.Example.com/some/path/"
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# PATCH — rotate secret, toggle enabled, re-derive domain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_rotates_secret_and_toggles_enabled(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from sqlalchemy import select

    from app.crypto import decrypt
    from app.models.manyfold import ManyfoldInstance

    csrf = await _setup_and_login(client)
    create_resp = await _create_instance(client, csrf, client_secret="original-secret")
    instance_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/admin/manyfold/{instance_id}",
        json={"client_secret": "new-secret-value", "enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["has_secret"] is True
    assert "client_secret" not in data

    # Confirm the underlying ciphertext actually rotated (not a no-op) by
    # decrypting straight from the DB, via the same session the app used.
    result = await db_session.execute(
        select(ManyfoldInstance).where(ManyfoldInstance.id == instance_id)
    )
    inst = result.scalar_one()
    assert decrypt(inst.client_secret_enc) == "new-secret-value"


@pytest.mark.asyncio
async def test_patch_re_derives_domain_and_guards_uniqueness(
    client: AsyncClient,
) -> None:
    csrf = await _setup_and_login(client)
    await _create_instance(client, csrf, base_url="https://taken.example.com")
    create_resp = await _create_instance(
        client, csrf, base_url="https://movable.example.com"
    )
    instance_id = create_resp.json()["id"]

    # Move to a free domain — should succeed and update `domain`.
    resp = await client.patch(
        f"/api/admin/manyfold/{instance_id}",
        json={"base_url": "https://new-home.example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["domain"] == "new-home.example.com"

    # Move to an already-taken domain — should 409 and not clobber the row.
    resp2 = await client.patch(
        f"/api/admin/manyfold/{instance_id}",
        json={"base_url": "https://taken.example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_patch_missing_instance_404(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    resp = await client.patch(
        "/api/admin/manyfold/999999",
        json={"enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_manyfold_instance(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    create_resp = await _create_instance(client, csrf)
    instance_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/admin/manyfold/{instance_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204

    resp2 = await client.get(f"/api/admin/manyfold/{instance_id}")
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Test-connection — monkeypatch the storage-layer seam
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_connection_success(client: AsyncClient, monkeypatch: Any) -> None:
    import app.storage.manyfold_client as mod

    def fake_caller(token_url: str, form: dict, timeout_s: float) -> tuple:
        assert form["grant_type"] == "client_credentials"
        assert form["client_id"] == "test-client-id"
        assert form["client_secret"] == "s3cr3t-value"
        return (
            200,
            {
                "access_token": "abc123",
                "token_type": "Bearer",
                "expires_in": 7200,
                "scope": "public read",
                "created_at": 1234567890,
            },
        )

    monkeypatch.setattr(mod, "_manyfold_token_caller", fake_caller)

    csrf = await _setup_and_login(client)
    create_resp = await _create_instance(client, csrf)
    instance_id = create_resp.json()["id"]
    assert create_resp.json()["last_connected_at"] is None

    resp = await client.post(
        f"/api/admin/manyfold/{instance_id}/test-connection",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["scope"] == "public read"

    # last_connected_at is now set.
    get_resp = await client.get(f"/api/admin/manyfold/{instance_id}")
    assert get_resp.json()["last_connected_at"] is not None


@pytest.mark.asyncio
async def test_test_connection_auth_failure(client: AsyncClient, monkeypatch: Any) -> None:
    import app.storage.manyfold_client as mod

    def fake_caller(token_url: str, form: dict, timeout_s: float) -> tuple:
        return (401, {"error": "invalid_client"})

    monkeypatch.setattr(mod, "_manyfold_token_caller", fake_caller)

    csrf = await _setup_and_login(client)
    create_resp = await _create_instance(client, csrf)
    instance_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/admin/manyfold/{instance_id}/test-connection",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "401" in data["message"] or "credentials" in data["message"].lower()

    # last_connected_at stays unset on failure.
    get_resp = await client.get(f"/api/admin/manyfold/{instance_id}")
    assert get_resp.json()["last_connected_at"] is None


@pytest.mark.asyncio
async def test_test_connection_scope_failure(client: AsyncClient, monkeypatch: Any) -> None:
    import app.storage.manyfold_client as mod

    def fake_caller(token_url: str, form: dict, timeout_s: float) -> tuple:
        return (403, {"error": "insufficient_scope"})

    monkeypatch.setattr(mod, "_manyfold_token_caller", fake_caller)

    csrf = await _setup_and_login(client)
    create_resp = await _create_instance(client, csrf)
    instance_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/admin/manyfold/{instance_id}/test-connection",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "403" in data["message"] or "scope" in data["message"].lower()


@pytest.mark.asyncio
async def test_test_connection_network_error(client: AsyncClient, monkeypatch: Any) -> None:
    import app.storage.manyfold_client as mod

    def fake_caller(token_url: str, form: dict, timeout_s: float) -> tuple:
        raise mod.ManyfoldConnectionError("Timed out connecting to the instance.")

    monkeypatch.setattr(mod, "_manyfold_token_caller", fake_caller)

    csrf = await _setup_and_login(client)
    create_resp = await _create_instance(client, csrf)
    instance_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/admin/manyfold/{instance_id}/test-connection",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "timed out" in data["message"].lower()


@pytest.mark.asyncio
async def test_test_connection_no_secret_configured(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """A row with no secret (e.g. created pre-secret) never calls the client."""
    import app.storage.manyfold_client as mod
    from app.models.manyfold import ManyfoldInstance

    calls: list[Any] = []

    def fake_caller(token_url: str, form: dict, timeout_s: float) -> tuple:
        calls.append(token_url)
        return (200, {"access_token": "x", "scope": "public read"})

    monkeypatch.setattr(mod, "_manyfold_token_caller", fake_caller)

    csrf = await _setup_and_login(client)

    # Create directly via the ORM so client_secret_enc stays null (the admin
    # API's CreateManyfoldInstanceRequest requires a secret on create).
    inst = ManyfoldInstance(
        base_url="https://no-secret.example.com",
        domain="no-secret.example.com",
        client_id="cid",
        client_secret_enc=None,
        scopes="public read",
        enabled=True,
    )
    db_session.add(inst)
    await db_session.flush()

    resp = await client.post(
        f"/api/admin/manyfold/{inst.id}/test-connection",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "secret" in data["message"].lower()
    assert calls == []  # the client was never invoked
