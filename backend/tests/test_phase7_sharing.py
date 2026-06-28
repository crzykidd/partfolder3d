"""Phase 7 sharing tests — security and functional.

SECURITY HEADLINE: these tests explicitly prove:
  1. Public share endpoints NEVER return private print records.
  2. Public share endpoints NEVER expose private records in their response.
  3. Expired share tokens return 403 (not the resource).
  4. Revoked share tokens return 403.
  5. Public share ZIP bundles never include private records
     (checked via bundle flags, not actual ZIP contents since worker needs arq).
  6. Instance-import (from-share-link) never transfers private records
     (remote endpoint is mocked to return only public data).
  7. Full-site share link exposes catalog browse but not per-item private data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.download_bundle import DownloadBundle

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


async def _setup_admin(client: AsyncClient) -> str:
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@sharetests.example",
            "admin_name": "Admin",
            "admin_password": "password1234",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@sharetests.example", "password": "password1234"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


async def _create_item(client: AsyncClient, csrf: str) -> tuple[int, str]:
    import tempfile

    tmpdir = tempfile.mkdtemp()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Share Test Library", "mount_path": tmpdir},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    lib_id = lib_resp.json()["id"]

    item_resp = await client.post(
        "/api/items",
        json={"title": "Shared Widget", "library_id": lib_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201
    data = item_resp.json()
    return data["id"], data["key"]


async def _create_records(
    client: AsyncClient, csrf: str, item_key: str
) -> tuple[int, int]:
    """Create one private and one public print record. Returns (private_id, public_id)."""
    priv = await client.post(
        f"/api/items/{item_key}/print-records",
        json={"note": "Secret private note", "visibility": "private", "success": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert priv.status_code == 201
    private_id = priv.json()["id"]

    pub = await client.post(
        f"/api/items/{item_key}/print-records",
        json={"note": "Public note for sharing", "visibility": "public", "success": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert pub.status_code == 201
    public_id = pub.json()["id"]

    return private_id, public_id


# ---------------------------------------------------------------------------
# Share link creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mint_item_share_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    resp = await client.post(
        f"/api/items/{key}/shares",
        json={"label": "Test link", "expires_days": 7},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["token"]) == 64  # 32 random bytes as hex
    assert data["scope"] == "item_design"
    assert data["revoked"] is False
    assert data["is_active"] is True
    assert data["label"] == "Test link"


@pytest.mark.asyncio
async def test_mint_site_share_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    csrf = await _setup_admin(client)

    resp = await client.post(
        "/api/admin/shares/site",
        json={"label": "Full site link", "expires_days": 0},  # never expires
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["scope"] == "full_site"
    assert data["expires_at"] is None  # never expires


@pytest.mark.asyncio
async def test_share_token_is_unguessable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two minted tokens must be different and 64 hex chars long."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    tokens = set()
    for _ in range(3):
        r = await client.post(
            f"/api/items/{key}/shares",
            json={},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 201
        token = r.json()["token"]
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)
        tokens.add(token)

    # All three tokens must be unique
    assert len(tokens) == 3


# ---------------------------------------------------------------------------
# SECURITY TEST 1: public endpoint never returns private records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_share_never_returns_private_records(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SECURITY: public share endpoint returns only public print records.

    Given:
      - An item with one private record and one public record
      - A valid share link for that item
    When:
      - An un-authenticated request fetches the public share endpoint
    Then:
      - The response contains the public record
      - The response does NOT contain the private record
      - Private note text does NOT appear anywhere in the response
    """
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)
    private_id, public_id = await _create_records(client, csrf, key)

    # Mint a share link
    mint_resp = await client.post(
        f"/api/items/{key}/shares",
        json={"expires_days": 7},
        headers={"X-CSRF-Token": csrf},
    )
    token = mint_resp.json()["token"]

    # Log out to test as unauthenticated
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    # Access public share endpoint (un-authenticated)
    resp = await client.get(f"/api/public/share/{token}")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    public_records = data.get("public_print_records", [])

    # Must contain exactly one record (the public one)
    assert len(public_records) == 1, (
        f"Expected 1 public record but got {len(public_records)}: {public_records}"
    )

    # The returned record must be the public one
    record = public_records[0]
    assert record["note"] == "Public note for sharing"

    # CRITICAL: private note must NOT appear in the response at all
    response_text = resp.text
    assert "Secret private note" not in response_text, (
        "SECURITY VIOLATION: private note text found in public share response!"
    )

    # CRITICAL: private record ID must not appear in the serialized records
    returned_ids = {r.get("id") for r in public_records}
    assert private_id not in returned_ids, (
        f"SECURITY VIOLATION: private record ID {private_id} found in public response!"
    )


@pytest.mark.asyncio
async def test_public_share_file_paths_not_exposed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SECURITY: public share response must not expose filesystem paths."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    # Create a public record
    await client.post(
        f"/api/items/{key}/print-records",
        json={"note": "Public", "visibility": "public"},
        headers={"X-CSRF-Token": csrf},
    )

    mint_resp = await client.post(
        f"/api/items/{key}/shares",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    token = mint_resp.json()["token"]
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    resp = await client.get(f"/api/public/share/{token}")
    assert resp.status_code == 200
    data = resp.json()

    # File paths must not be in the serialized print records
    for rec in data.get("public_print_records", []):
        assert "gcode_file_path" not in rec, (
            "gcode_file_path should not be exposed in public share response"
        )
        assert "print_photo_path" not in rec, (
            "print_photo_path should not be exposed in public share response"
        )


# ---------------------------------------------------------------------------
# SECURITY TEST 2: expired token returns 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_share_link_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SECURITY: expired share link returns 403, not the resource."""
    from app.models.item import Item  # noqa: PLC0415
    from app.models.share_link import ShareLink  # noqa: PLC0415

    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    # Insert an already-expired share link directly into DB
    item_result = await db_session.execute(select(Item).where(Item.key == key))
    item = item_result.scalar_one()

    expired_link = ShareLink(
        scope="item_design",
        item_id=item.id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),  # already expired
    )
    db_session.add(expired_link)
    await db_session.flush()

    resp = await client.get(f"/api/public/share/{expired_link.token}")
    assert resp.status_code == 403, (
        f"Expected 403 for expired link but got {resp.status_code}: {resp.text}"
    )
    assert "expired" in resp.text.lower()


# ---------------------------------------------------------------------------
# SECURITY TEST 3: revoked token returns 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoked_share_link_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SECURITY: revoked share link returns 403 immediately after revocation."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    # Mint a link
    mint_resp = await client.post(
        f"/api/items/{key}/shares",
        json={"expires_days": 30},
        headers={"X-CSRF-Token": csrf},
    )
    assert mint_resp.status_code == 201
    share = mint_resp.json()
    share_id = share["id"]
    token = share["token"]

    # Verify it works
    resp = await client.get(f"/api/public/share/{token}")
    assert resp.status_code == 200

    # Revoke it
    revoke_resp = await client.post(
        f"/api/shares/{share_id}/revoke",
        headers={"X-CSRF-Token": csrf},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked"] is True

    # Now accessing it should return 403
    resp2 = await client.get(f"/api/public/share/{token}")
    assert resp2.status_code == 403, (
        f"Expected 403 for revoked link but got {resp2.status_code}: {resp2.text}"
    )
    assert "revoked" in resp2.text.lower()


# ---------------------------------------------------------------------------
# SECURITY TEST 4: public ZIP bundle flags prevent private data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_share_zip_bundle_is_anonymous(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SECURITY: ZIP bundles queued via public share links have requester_user_id=None.

    This is a critical security invariant: the worker checks requester_user_id=None
    and includes only public records (or no print history when include_print_history=False).

    We verify the bundle row in the DB has the correct security flags.
    Note: the actual ZIP build is done by the worker (not testable without arq),
    but the flags on the DownloadBundle row determine what gets included.
    """
    csrf = await _setup_admin(client)
    item_id, key = await _create_item(client, csrf)

    # Create a private record
    await client.post(
        f"/api/items/{key}/print-records",
        json={"note": "PRIVATE TOP SECRET", "visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    )

    # Mint a share link
    mint_resp = await client.post(
        f"/api/items/{key}/shares",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    token = mint_resp.json()["token"]

    # Log out (public request)
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    # Request a public ZIP via the share link
    resp = await client.post(f"/api/public/share/{token}/zip")
    assert resp.status_code == 200
    bundle_id = resp.json()["id"]

    # Load the bundle row from DB
    bundle_result = await db_session.execute(
        select(DownloadBundle).where(DownloadBundle.id == bundle_id)
    )
    bundle = bundle_result.scalar_one_or_none()
    assert bundle is not None

    # SECURITY ASSERTIONS:
    assert bundle.requester_user_id is None, (
        "SECURITY VIOLATION: public bundle must have requester_user_id=None! "
        f"Got {bundle.requester_user_id}"
    )
    assert bundle.include_print_history is False, (
        "SECURITY: public share ZIP must never include print history! "
        f"Got include_print_history={bundle.include_print_history}"
    )


@pytest.mark.asyncio
async def test_authenticated_zip_with_history_sets_user_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An authenticated download with include_history=True sets requester_user_id."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    resp = await client.post(
        f"/api/items/{key}/zip?include_history=true",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    bundle_id = resp.json()["id"]

    bundle_result = await db_session.execute(
        select(DownloadBundle).where(DownloadBundle.id == bundle_id)
    )
    bundle = bundle_result.scalar_one_or_none()
    assert bundle is not None

    # Authenticated user: requester_user_id must be set
    assert bundle.requester_user_id is not None, (
        "Authenticated download should set requester_user_id"
    )
    assert bundle.include_print_history is True


# ---------------------------------------------------------------------------
# Share audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_audit_records_events(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Audit events are recorded for mint, view, and revoke actions."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    # Mint a link (records "created" event)
    mint_resp = await client.post(
        f"/api/items/{key}/shares",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert mint_resp.status_code == 201
    share_id = mint_resp.json()["id"]
    token = mint_resp.json()["token"]

    # Access the public endpoint (records "accessed_view" event)
    view_resp = await client.get(f"/api/public/share/{token}")
    assert view_resp.status_code == 200

    # Check audit log
    audit_resp = await client.get(f"/api/shares/{share_id}/audit")
    assert audit_resp.status_code == 200
    events = audit_resp.json()

    event_types = {e["event_type"] for e in events}
    assert "created" in event_types, f"Expected 'created' event, got: {event_types}"
    assert "accessed_view" in event_types, (
        f"Expected 'accessed_view' event, got: {event_types}"
    )


@pytest.mark.asyncio
async def test_revoke_records_audit_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Revocation records a 'revoked' audit event."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    mint_resp = await client.post(
        f"/api/items/{key}/shares", json={}, headers={"X-CSRF-Token": csrf}
    )
    share_id = mint_resp.json()["id"]

    await client.post(f"/api/shares/{share_id}/revoke", headers={"X-CSRF-Token": csrf})

    audit_resp = await client.get(f"/api/shares/{share_id}/audit")
    events = audit_resp.json()
    event_types = {e["event_type"] for e in events}
    assert "revoked" in event_types


# ---------------------------------------------------------------------------
# SECURITY TEST 5: from-share-link never imports private records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_instance_import_never_transfers_private_records(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SECURITY: from-share-link only processes what the remote share endpoint returns.

    The remote public endpoint only returns public records.  We mock the remote
    fetch to return a response that includes only public data.  Private records
    must never appear in the created ImportSession.
    """
    import app.routers.import_sessions as import_sessions_mod

    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    # Create a library for the import
    import tempfile
    tmpdir = tempfile.mkdtemp()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Import Library", "mount_path": tmpdir},
        headers={"X-CSRF-Token": csrf},
    )
    lib_id = lib_resp.json()["id"]

    # Mock the remote fetch — returns only public data (as a real remote would)
    # CRITICAL: no private records in this response
    MOCK_REMOTE_RESPONSE = {
        "key": "abc123",
        "title": "Remote Widget",
        "description": "A great widget",
        "license": "CC-BY",
        "source_url": None,
        "source_site": None,
        "tags": ["fdm", "functional"],
        "public_print_records": [
            {
                "note": "Public print note",
                "date": "2026-01-01",
                "success": True,
                "rating": 4,
                "filament_length_mm": 500.0,
                # NOTE: no 'logged_by_id', no private-record fields
            }
        ],
        # IMPORTANT: no "private_print_records" or "all_print_records" field
    }

    def mock_fetcher(url: str, timeout: int) -> dict:
        # Validate we're fetching the API URL (not the UI URL)
        assert "/api/public/share/" in url
        return MOCK_REMOTE_RESPONSE

    original = import_sessions_mod._share_link_fetcher
    import_sessions_mod._share_link_fetcher = mock_fetcher

    # Also patch socket.getaddrinfo so the SSRF guard sees a public IP for
    # 'remote.example.com' (in CI there is no DNS for this test domain, and the
    # guard runs before the mock fetcher is called).
    import socket
    from unittest.mock import patch

    def _fake_getaddrinfo(host: str, port: object, *a: object, **kw: object) -> list:
        # Return a single public IP so the SSRF pre-flight check passes.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0))]

    try:
        fake_token = "a" * 64  # 64-char hex-like string
        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo):
            resp = await client.post(
                "/api/import-sessions/from-share-link",
                json={
                    "share_url": f"https://remote.example.com/share/{fake_token}",
                    "library_id": lib_id,
                    "include_public_notes": True,
                    "include_gcode": False,
                    "include_photos": True,
                    "include_settings": True,
                },
                headers={"X-CSRF-Token": csrf},
            )
        assert resp.status_code == 201, resp.text
        session_data = resp.json()

        # The session should have the remote title
        assert session_data["confirmed_title"] == "Remote Widget"
        assert session_data["status"] == "pending_wizard"

        # Check the raw DB session for the absence of any "private" data
        import uuid  # noqa: PLC0415

        from app.models.import_session import ImportSession  # noqa: PLC0415

        sid = uuid.UUID(session_data["id"])
        sess_result = await db_session.execute(
            select(ImportSession).where(ImportSession.id == sid)
        )
        session_row = sess_result.scalar_one_or_none()
        assert session_row is not None

        # Verify the tag_state contains the imported public records
        ts = session_row.tag_state or {}
        imported_records = ts.get("imported_print_records", [])
        # The one public record should be there
        assert len(imported_records) == 1
        assert imported_records[0]["note"] == "Public print note"

        # CRITICAL: search entire session JSON for any private indicator
        import json
        session_json = json.dumps(ts)
        # No "private" word should appear from a private record's visibility field
        # (the public record has success=True which is fine)
        assert "Secret" not in session_json
        assert "PRIVATE" not in session_json

    finally:
        import_sessions_mod._share_link_fetcher = original


# ---------------------------------------------------------------------------
# Full-site share link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_site_share_catalog_browse(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Full-site share link allows catalog browse (public read-only)."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    # Mint a full-site link
    site_resp = await client.post(
        "/api/admin/shares/site",
        json={"label": "Site link", "expires_days": 7},
        headers={"X-CSRF-Token": csrf},
    )
    assert site_resp.status_code == 201
    token = site_resp.json()["token"]

    # Log out
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    # Access catalog via full-site link
    resp = await client.get(f"/api/public/share/{token}/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_full_site_link_cannot_access_item_endpoint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Full-site link token cannot be used to access the item_design endpoint."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    site_resp = await client.post(
        "/api/admin/shares/site",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    token = site_resp.json()["token"]
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    # Trying to use a full_site token as if it were item_design → 400
    resp = await client.get(f"/api/public/share/{token}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_item_link_cannot_access_catalog(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Item-design link token cannot be used to access the catalog endpoint."""
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    mint_resp = await client.post(
        f"/api/items/{key}/shares",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    token = mint_resp.json()["token"]
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    # Item-design token cannot browse catalog
    resp = await client.get(f"/api/public/share/{token}/catalog")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# List and non-owner revoke guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_item_shares(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    csrf = await _setup_admin(client)
    _, key = await _create_item(client, csrf)

    for _ in range(2):
        await client.post(
            f"/api/items/{key}/shares",
            json={},
            headers={"X-CSRF-Token": csrf},
        )

    list_resp = await client.get(f"/api/items/{key}/shares")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2
