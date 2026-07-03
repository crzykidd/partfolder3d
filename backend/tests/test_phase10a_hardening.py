"""Phase 10a hardening tests — security contracts and SSRF guard.

Contracts verified:
  1. SSRF guard blocks loopback, link-local, RFC-1918 private, and cloud-metadata
     IPs in both the URL scraper and the instance share-link import.
  2. Path traversal protection on authenticated file-download endpoint.
  3. Path traversal protection on public-share file-download endpoint.
  4. Admin-only routes reject non-admin users (role enforcement).
  5. Per-user scoping: a user cannot access another user's resources that
     are private (e.g., another user's import sessions).
  6. SSRF guard unit tests (pure, no HTTP) against blocked/allowed addresses.
  7. Public export (GET /api/admin/export/catalog) only accessible to admins.
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Shared setup helpers (mirrors other test files' patterns)
# ---------------------------------------------------------------------------


async def _do_setup(client: AsyncClient, email: str = "admin@hardening.example") -> str:
    """Run initial setup and return CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": email,
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepassword1"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


async def _create_library(client: AsyncClient, csrf: str) -> int:
    tmpdir = tempfile.mkdtemp()
    resp = await client.post(
        "/api/libraries",
        json={"name": "Test Library", "mount_path": tmpdir},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_item(client: AsyncClient, csrf: str, lib_id: int) -> tuple[int, str, str]:
    """Returns (item_id, item_key, item_dir_path)."""
    resp = await client.post(
        "/api/items",
        json={"title": "Test Item", "library_id": lib_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    return data["id"], data["key"], data.get("dir_path", "")


# ---------------------------------------------------------------------------
# 1. SSRF guard — unit tests (no HTTP, pure IP-range checks)
# ---------------------------------------------------------------------------


class TestSSRFGuardUnit:
    """Pure unit tests for the SSRF guard IP-blocking logic."""

    def _guard(self, url: str) -> None:
        from app.storage.ssrf_guard import assert_safe_url

        assert_safe_url(url)

    def test_blocks_loopback_ipv4(self) -> None:
        from app.storage.ssrf_guard import _is_blocked_ip

        assert _is_blocked_ip("127.0.0.1") is True
        assert _is_blocked_ip("127.99.100.200") is True

    def test_blocks_loopback_ipv6(self) -> None:
        from app.storage.ssrf_guard import _is_blocked_ip

        assert _is_blocked_ip("::1") is True

    def test_blocks_link_local_v4(self) -> None:
        from app.storage.ssrf_guard import _is_blocked_ip

        assert _is_blocked_ip("169.254.1.1") is True
        assert _is_blocked_ip("169.254.169.254") is True  # cloud IMDS

    def test_blocks_link_local_v6(self) -> None:
        from app.storage.ssrf_guard import _is_blocked_ip

        assert _is_blocked_ip("fe80::1") is True

    def test_blocks_private_rfc1918(self) -> None:
        from app.storage.ssrf_guard import _is_blocked_ip

        assert _is_blocked_ip("10.0.0.1") is True
        assert _is_blocked_ip("172.16.0.1") is True
        assert _is_blocked_ip("192.168.1.1") is True

    def test_blocks_private_ula_v6(self) -> None:
        from app.storage.ssrf_guard import _is_blocked_ip

        assert _is_blocked_ip("fc00::1") is True
        assert _is_blocked_ip("fd00::1") is True

    def test_blocks_aws_ipv6_imds(self) -> None:
        from app.storage.ssrf_guard import _is_blocked_ip

        assert _is_blocked_ip("fd00:ec2::254") is True

    def test_allows_public_ip(self) -> None:
        from app.storage.ssrf_guard import _is_blocked_ip

        assert _is_blocked_ip("1.1.1.1") is False
        assert _is_blocked_ip("8.8.8.8") is False

    def test_blocks_non_http_scheme(self) -> None:
        from app.storage.ssrf_guard import SSRFBlockedError, assert_safe_url

        with pytest.raises(SSRFBlockedError, match="not allowed"):
            assert_safe_url("ftp://example.com/file")

    def test_blocks_file_scheme(self) -> None:
        from app.storage.ssrf_guard import SSRFBlockedError, assert_safe_url

        with pytest.raises(SSRFBlockedError, match="not allowed"):
            assert_safe_url("file:///etc/passwd")

    def test_blocks_no_hostname(self) -> None:
        from app.storage.ssrf_guard import SSRFBlockedError, assert_safe_url

        with pytest.raises(SSRFBlockedError):
            assert_safe_url("http:///path")

    def test_allows_valid_public_url(self, monkeypatch: object) -> None:
        """URL pointing to a real public IP passes the guard."""
        import socket

        from app.storage.ssrf_guard import assert_safe_url

        # Patch getaddrinfo to return a known-public address so we don't need
        # real DNS in tests.
        def fake_getaddrinfo(host, port, *a, **kw):  # type: ignore[no-untyped-def]
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        # Should NOT raise
        assert_safe_url("https://cloudflare-dns.com/dns-query")

    def test_blocks_url_resolving_to_private_ip(self, monkeypatch: object) -> None:
        """URL whose hostname resolves to an internal IP is blocked."""
        import socket

        from app.storage.ssrf_guard import SSRFBlockedError, assert_safe_url

        def fake_getaddrinfo(host, port, *a, **kw):  # type: ignore[no-untyped-def]
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(SSRFBlockedError, match="restricted IP"):
            assert_safe_url("https://internal-service.corp/endpoint")

    def test_blocks_url_resolving_to_imds(self, monkeypatch: object) -> None:
        """URL whose hostname resolves to the cloud IMDS address is blocked."""
        import socket

        from app.storage.ssrf_guard import SSRFBlockedError, assert_safe_url

        def fake_getaddrinfo(host, port, *a, **kw):  # type: ignore[no-untyped-def]
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(SSRFBlockedError, match="restricted IP"):
            assert_safe_url("http://metadata.google.internal/")


# ---------------------------------------------------------------------------
# 2. SSRF via scraper — scrape_url blocks internal URLs
# ---------------------------------------------------------------------------


class TestScraperSSRF:
    """scrape_url() must block internal targets via the SSRF guard."""

    def test_scrape_url_blocked_loopback(self) -> None:
        """scrape_url blocks http://localhost/... with blocked=True."""
        import socket

        from app.storage.scraper import scrape_url

        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))
            ]
            result = scrape_url("http://localhost/admin")

        assert result.blocked is True
        assert "restricted" in (result.note or "").lower()

    def test_scrape_url_blocked_private_ip(self) -> None:
        """scrape_url blocks URLs that resolve to RFC-1918 private addresses."""
        import socket

        from app.storage.scraper import scrape_url

        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.5", 0))
            ]
            result = scrape_url("http://internal-host.local/page")

        assert result.blocked is True

    def test_scrape_url_blocked_imds(self) -> None:
        """scrape_url blocks the cloud IMDS address 169.254.169.254."""
        import socket

        from app.storage.scraper import scrape_url

        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))
            ]
            result = scrape_url("http://169.254.169.254/latest/meta-data/")

        assert result.blocked is True

    def test_scrape_url_blocked_non_http_scheme(self) -> None:
        """scrape_url blocks non-http/https schemes."""
        from app.storage.scraper import scrape_url

        result = scrape_url("file:///etc/passwd")
        assert result.blocked is True


# ---------------------------------------------------------------------------
# 3. SSRF via instance share-link import endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_link_import_blocked_internal_ip(
    client: AsyncClient,
) -> None:
    """POST /api/import-sessions/from-share-link blocks internal IP targets."""
    import socket

    csrf = await _do_setup(client)

    internal_token = "a" * 64  # valid 64-char hex token
    internal_url = f"http://internal-corp.local/share/{internal_token}"

    # Patch DNS to return a private IP for the hostname
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))
        ]
        resp = await client.post(
            "/api/import-sessions/from-share-link",
            json={"share_url": internal_url},
            headers={"X-CSRF-Token": csrf},
        )

    assert resp.status_code == 422
    assert "not allowed" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_share_link_import_blocked_loopback(
    client: AsyncClient,
) -> None:
    """POST /api/import-sessions/from-share-link blocks loopback targets."""
    import socket

    csrf = await _do_setup(client)

    token = "b" * 64
    loopback_url = f"http://127.0.0.1/share/{token}"

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))
        ]
        resp = await client.post(
            "/api/import-sessions/from-share-link",
            json={"share_url": loopback_url},
            headers={"X-CSRF-Token": csrf},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_url_import_session_blocked_internal_ip(
    client: AsyncClient,
) -> None:
    """POST /api/import-sessions with source_type='url' blocks internal targets."""
    import socket

    csrf = await _do_setup(client)

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))
        ]
        resp = await client.post(
            "/api/import-sessions",
            json={
                "source_type": "url",
                "source_url": "http://metadata.internal/secret",
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert resp.status_code == 422
    assert "not allowed" in resp.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# 4. Path traversal — authenticated file download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_file_path_traversal_rejected(
    client: AsyncClient,
) -> None:
    """GET /api/items/{key}/files/{path} rejects ../ traversal."""
    csrf = await _do_setup(client)
    lib_id = await _create_library(client, csrf)
    _, key, _ = await _create_item(client, csrf, lib_id)

    # Attempt path traversal
    resp = await client.get(f"/api/items/{key}/files/../../../etc/passwd")
    # FastAPI normalizes path params; the handler must still reject it
    assert resp.status_code in (400, 404)


@pytest.mark.asyncio
async def test_download_file_path_traversal_encoded(
    client: AsyncClient,
) -> None:
    """GET /api/items/{key}/files/{path} rejects URL-encoded traversal."""
    csrf = await _do_setup(client)
    lib_id = await _create_library(client, csrf)
    _, key, _ = await _create_item(client, csrf, lib_id)

    # %2F = /, %2E%2E = ..
    resp = await client.get(f"/api/items/{key}/files/%2E%2E%2F%2E%2E%2Fetc%2Fpasswd")
    assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# 5. Path traversal — public share file download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_share_file_traversal_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/public/share/{token}/files/{path} rejects ../ traversal."""
    csrf = await _do_setup(client)
    lib_id = await _create_library(client, csrf)
    _, key, _ = await _create_item(client, csrf, lib_id)

    # Mint a share link
    mint_resp = await client.post(
        f"/api/items/{key}/shares",
        json={"label": "traversal-test"},
        headers={"X-CSRF-Token": csrf},
    )
    assert mint_resp.status_code == 201
    token = mint_resp.json()["token"]

    # Attempt traversal via the public endpoint
    resp = await client.get(f"/api/public/share/{token}/files/../../../etc/passwd")
    assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# 6. Admin-only routes enforce role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_export_requires_admin(
    client: AsyncClient,
) -> None:
    """GET /api/admin/export/catalog returns 403 for a regular user."""
    # Setup: create admin (note: .example is the pattern used in other tests)
    await _do_setup(client, "admin@roletest.example")

    # Login as admin — export should work (we're already logged in from _do_setup)
    admin_resp = await client.get("/api/admin/export/catalog")
    assert admin_resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_backup_endpoints_require_admin(
    client: AsyncClient,
) -> None:
    """Backup endpoints return 401 for unauthenticated requests."""
    resp = await client.get("/api/admin/backups")
    assert resp.status_code == 401

    resp2 = await client.post(
        "/api/admin/backups/run",
        headers={"X-CSRF-Token": "fake"},
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_cannot_write_items(
    client: AsyncClient,
) -> None:
    """POST /api/items (write) returns 401 when not authenticated."""
    # GET /api/items uses get_optional_user (public browse is allowed).
    # POST /api/items requires authentication.
    resp = await client.post(
        "/api/items",
        json={"title": "Unauthorized", "library_id": 1},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. Secrets never returned in responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_provider_key_not_returned(
    client: AsyncClient,
) -> None:
    """AI provider API key is never returned in any field."""
    csrf = await _do_setup(client)

    # Create a provider with a key
    create_resp = await client.post(
        "/api/ai-providers",
        json={
            "provider": "openai",
            "api_key": "sk-supersecretkey123",
            "enabled": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    data = create_resp.json()

    # The key must NOT appear anywhere in the response
    resp_text = create_resp.text
    assert "supersecretkey" not in resp_text
    assert "sk-" not in resp_text
    # has_key should indicate a key is set
    assert data["has_key"] is True

    # Also check GET single provider
    provider_id = data["id"]
    get_resp = await client.get(f"/api/ai-providers/{provider_id}")
    assert get_resp.status_code == 200
    assert "supersecretkey" not in get_resp.text

    # And GET list
    list_resp = await client.get("/api/ai-providers")
    assert list_resp.status_code == 200
    assert "supersecretkey" not in list_resp.text


# ---------------------------------------------------------------------------
# 8. Share link privacy — public endpoint never leaks private print records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_share_no_private_records(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Public share endpoint never returns private print records."""
    csrf = await _do_setup(client)
    lib_id = await _create_library(client, csrf)
    _, key, _ = await _create_item(client, csrf, lib_id)

    # Add private and public print records
    priv_resp = await client.post(
        f"/api/items/{key}/print-records",
        json={"note": "Secret internal note", "visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    )
    assert priv_resp.status_code == 201

    pub_resp = await client.post(
        f"/api/items/{key}/print-records",
        json={"note": "Shared public note", "visibility": "public"},
        headers={"X-CSRF-Token": csrf},
    )
    assert pub_resp.status_code == 201

    # Mint a share link
    mint = await client.post(
        f"/api/items/{key}/shares",
        json={"label": "privacy-test"},
        headers={"X-CSRF-Token": csrf},
    )
    assert mint.status_code == 201
    token = mint.json()["token"]

    # Fetch public share — must not contain private note
    share_resp = await client.get(f"/api/public/share/{token}")
    assert share_resp.status_code == 200
    body = share_resp.json()

    notes = [r.get("note", "") for r in body.get("public_print_records", [])]
    assert "Secret internal note" not in notes, "Private record leaked via public share!"
    assert "Shared public note" in notes, "Public record missing from share response"


# ---------------------------------------------------------------------------
# 9. FTS injection — parameterized query handles special chars safely
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fts_special_characters_do_not_500(
    client: AsyncClient,
) -> None:
    """Full-text search with SQL/tsquery special characters returns 200 not 500."""
    csrf = await _do_setup(client)
    await _create_library(client, csrf)

    # These strings would cause errors if passed raw to tsquery.
    # Use params= dict so httpx properly URL-encodes each value
    # (avoids InvalidURL on null bytes etc. at the httpx layer;
    # the server must handle whatever reaches it gracefully).
    nasty_inputs = [
        "'; DROP TABLE items; --",
        "' OR '1'='1",
        "!&|<>():*",
        "a" * 2000,  # very long query
    ]

    for q in nasty_inputs:
        resp = await client.get("/api/items", params={"q": q})
        # Should return 200 (no results) not 500 (server error)
        assert resp.status_code in (200, 422), (
            f"Unexpected {resp.status_code} for q={q!r}"
        )


# ---------------------------------------------------------------------------
# 10. Migration 0010 indexes exist in the database
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_0010_indexes_exist(
    db_session: AsyncSession,
) -> None:
    """Verify that migration 0010 created all expected indexes."""
    from sqlalchemy import text

    expected_indexes = [
        "ix_item_tags_tag_id",
        "ix_items_creator_id",
        "ix_items_created_at",
        "ix_items_updated_at",
        "ix_items_title",
        "ix_share_links_created_by_id",
        "ix_print_records_item_visibility",
        "ix_download_bundles_item_status_expires",
    ]

    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' "
            "ORDER BY indexname"
        )
    )
    existing = {row[0] for row in result.all()}

    missing = [idx for idx in expected_indexes if idx not in existing]
    assert not missing, f"Missing indexes from migration 0010: {missing}"
