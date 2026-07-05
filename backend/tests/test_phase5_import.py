"""Phase 5 tests: import sessions, tag reconciliation, site capabilities, tag approval.

Uses the same ephemeral Postgres + per-test rollback approach as earlier phases.
Scrape-related tests use local fixtures — no real network calls.
"""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site_capability import SiteToken
from app.models.tag import Tag, TagAlias, TagStatus


def _fake_public_getaddrinfo(host, port, *a, **kw):  # type: ignore[no-untyped-def]
    """Resolve any hostname to a public IP so the SSRF pre-flight passes offline."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient, tmp_path: Path) -> str:
    """Initialize instance and log in as admin; returns CSRF token."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@test.com",
            "admin_name": "Admin User",
            "admin_password": "adminpassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "adminpassword1"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


# ---------------------------------------------------------------------------
# Tag reconciliation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_tags_exact_match(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Tags that exist exactly are classified as confirmed."""
    from app.routers.import_sessions import reconcile_tags  # noqa: PLC0415

    # Create an active tag
    tag = Tag(name="fdm", status=TagStatus.active)
    db_session.add(tag)
    await db_session.flush()

    result = await reconcile_tags(db_session, ["fdm", "unknown-tag-xyz"])
    assert "fdm" in result["confirmed"]
    assert "unknown-tag-xyz" in result["pending"]
    assert "unknown-tag-xyz" not in result["confirmed"]


@pytest.mark.asyncio
async def test_reconcile_tags_alias_mapping(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Tags that match an alias are mapped to the canonical name."""
    from app.routers.import_sessions import reconcile_tags  # noqa: PLC0415

    canonical = Tag(name="fused-deposition-modeling", status=TagStatus.active)
    db_session.add(canonical)
    await db_session.flush()

    alias = TagAlias(alias="fdm-printing", tag_id=canonical.id)
    db_session.add(alias)
    await db_session.flush()

    result = await reconcile_tags(db_session, ["fdm-printing", "new-tag"])
    assert "fused-deposition-modeling" in result["confirmed"]
    assert "fdm-printing" not in result["confirmed"]
    assert "new-tag" in result["pending"]


@pytest.mark.asyncio
async def test_reconcile_tags_empty(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Empty tag list returns empty confirmed and pending."""
    from app.routers.import_sessions import reconcile_tags  # noqa: PLC0415

    result = await reconcile_tags(db_session, [])
    assert result == {"confirmed": [], "pending": []}


# ---------------------------------------------------------------------------
# Import session CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_url_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Create a URL-type import session; verify status=processing."""
    csrf = await _setup_and_login(client, tmp_path)

    # Create a library first
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Test Library", "mount_path": str(tmp_path / "lib")},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    library_id = lib_resp.json()["id"]

    # Create session (enqueue is fire-and-forget; it may fail with no Redis)
    resp = await client.post(
        "/api/import-sessions",
        json={
            "source_type": "url",
            "source_url": "https://example.com/thing/12345",
            "library_id": library_id,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_type"] == "url"
    assert data["status"] == "processing"
    assert data["source_url"] == "https://example.com/thing/12345"


@pytest.mark.asyncio
async def test_create_upload_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Create an upload-type import session; verify status=draft and staging_dir set."""
    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_type"] == "upload"
    assert data["status"] == "draft"
    assert data["staging_dir"] is not None


@pytest.mark.asyncio
async def test_get_import_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Retrieve an import session by ID."""
    csrf = await _setup_and_login(client, tmp_path)

    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/import-sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == session_id


@pytest.mark.asyncio
async def test_list_import_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """List import sessions returns only pending (non-committed/cancelled)."""
    csrf = await _setup_and_login(client, tmp_path)

    # Create two sessions
    for _ in range(2):
        await client.post(
            "/api/import-sessions",
            json={"source_type": "upload"},
            headers={"X-CSRF-Token": csrf},
        )

    list_resp = await client.get("/api/import-sessions")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_patch_import_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Patch wizard fields on a draft session."""
    csrf = await _setup_and_login(client, tmp_path)

    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/import-sessions/{session_id}",
        json={
            "confirmed_title": "My Cool Print",
            "description": "A great model",
            "confirmed_tags": [],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["confirmed_title"] == "My Cool Print"
    assert data["description"] == "A great model"


@pytest.mark.asyncio
async def test_cancel_import_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Cancelling a session sets status=cancelled."""
    csrf = await _setup_and_login(client, tmp_path)

    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    session_id = create_resp.json()["id"]

    cancel_resp = await client.post(
        f"/api/import-sessions/{session_id}/cancel",
        headers={"X-CSRF-Token": csrf},
    )
    assert cancel_resp.status_code == 204

    get_resp = await client.get(f"/api/import-sessions/{session_id}")
    # cancelled sessions are not in the default list; get by ID still works
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Share-link stub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_link_stub(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Share-link import endpoint is now implemented (Phase 7).

    Without a body it returns 422 (Unprocessable Entity — share_url required).
    The endpoint accepts POST with JSON body {share_url: ...} and returns 201 on
    success.  Full tests are in test_phase7_sharing.py.
    """
    csrf = await _setup_and_login(client, tmp_path)

    # Without a body → 422 (share_url is required)
    resp = await client.post(
        "/api/import-sessions/from-share-link",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Site capabilities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_site_capabilities_empty(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Empty site_capabilities returns an empty list."""
    await _setup_and_login(client, tmp_path)

    resp = await client.get("/api/site-capabilities")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_patch_site_capability(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """PATCH /api/site-capabilities/{domain} creates or updates a capability record."""
    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.patch(
        "/api/site-capabilities/thingiverse.com",
        json={"is_manual_only": True, "notes": "Requires auth"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "thingiverse.com"
    assert data["is_manual_only"] is True
    assert data["notes"] == "Requires auth"


@pytest.mark.asyncio
async def test_site_capability_token_encrypted(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Storing a site token encrypts it; plaintext is never in the DB."""
    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.patch(
        "/api/site-capabilities/printables.com",
        json={"requires_token": True, "token": "my-secret-api-token"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["has_token"] is True

    # Verify the stored token is encrypted (not plaintext)
    result = await db_session.execute(
        select(SiteToken).where(SiteToken.domain == "printables.com")
    )
    token_row = result.scalar_one_or_none()
    assert token_row is not None
    assert token_row.encrypted_token != "my-secret-api-token"
    assert token_row.encrypted_token.startswith("gAAAAA")  # Fernet prefix

    # Verify decryption works
    from app.crypto import decrypt  # noqa: PLC0415
    assert decrypt(token_row.encrypted_token) == "my-secret-api-token"


# ---------------------------------------------------------------------------
# Tag approval (Phase 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_pending_tag(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/tags/{id}/approve promotes a pending tag to active."""
    csrf = await _setup_and_login(client, tmp_path)

    # Create a pending tag directly in the DB
    tag = Tag(name="my-pending-tag", status=TagStatus.pending)
    db_session.add(tag)
    await db_session.flush()

    resp = await client.post(
        f"/api/tags/{tag.id}/approve",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["name"] == "my-pending-tag"


@pytest.mark.asyncio
async def test_approve_nonexistent_tag(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Approving a non-existent tag returns 404."""
    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.post(
        "/api/tags/99999/approve",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_already_active_tag_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Approving an already-active tag returns 200 (idempotent)."""
    csrf = await _setup_and_login(client, tmp_path)

    tag = Tag(name="already-active", status=TagStatus.active)
    db_session.add(tag)
    await db_session.flush()

    resp = await client.post(
        f"/api/tags/{tag.id}/approve",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


# ---------------------------------------------------------------------------
# Import commit: new tags must be created as pending (fix regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_new_tag_created_as_pending(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Committing an import session creates brand-new tags as status=pending.

    An existing active tag must remain active (just linked, not downgraded).
    This ensures new tags from the import wizard enter the admin approval queue
    rather than becoming immediately canonical and bypassing review.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from app.models.import_session import ImportSession, ImportSessionStatus  # noqa: PLC0415
    from app.models.tag import Tag, TagStatus  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)

    # Create a library with a temp mount path so the commit can write files.
    lib_path = tmp_path / "lib"
    lib_path.mkdir()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Commit Test Lib", "mount_path": str(lib_path)},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    library_id = lib_resp.json()["id"]

    # Pre-create an active canonical tag (simulates a tag already in the catalog).
    existing_tag = Tag(name="existing-canonical", status=TagStatus.active)
    db_session.add(existing_tag)
    await db_session.flush()

    # Create an upload import session (starts as draft; no files needed).
    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    # Directly set the session to pending_wizard with a hand-crafted tag_state
    # that includes a brand-new tag name not yet in the database.  This bypasses
    # reconcile_tags so we can inject an unknown confirmed tag and verify that
    # the commit path creates it as pending rather than active.
    res = await db_session.execute(
        select(ImportSession).where(ImportSession.id == session_id)
    )
    sess = res.scalar_one()
    sess.status = ImportSessionStatus.pending_wizard
    sess.confirmed_title = "Tag Status Test Item"
    sess.library_id = library_id
    sess.tag_state = {
        "confirmed": ["existing-canonical", "brand-new-tag"],
        "pending": [],
    }
    await db_session.flush()

    # Commit the session.
    commit_resp = await client.post(
        f"/api/import-sessions/{session_id}/commit",
        headers={"X-CSRF-Token": csrf},
    )
    assert commit_resp.status_code == 200, commit_resp.text

    # Existing active tag stays active — commit must not downgrade it.
    res = await db_session.execute(
        select(Tag).where(Tag.name == "existing-canonical")
    )
    tag_existing = res.scalar_one_or_none()
    assert tag_existing is not None
    assert tag_existing.status == TagStatus.active, (
        "An existing active tag must remain active after import commit"
    )

    # Brand-new tag must be created as pending (not active) so it enters the
    # admin approval queue.
    res = await db_session.execute(
        select(Tag).where(Tag.name == "brand-new-tag")
    )
    tag_new = res.scalar_one_or_none()
    assert tag_new is not None, "New tag should be created at commit time"
    assert tag_new.status == TagStatus.pending, (
        "Tags first seen during an import commit must be status=pending "
        "so they appear in the admin approval queue before becoming canonical"
    )

    # Verify the new pending tag appears via the admin pending-tags endpoint.
    pending_resp = await client.get("/api/admin/tags/pending")
    assert pending_resp.status_code == 200
    pending_names = [t["name"] for t in pending_resp.json()]
    assert "brand-new-tag" in pending_names, (
        f"brand-new-tag not in pending list; got: {pending_names}"
    )
    # Existing canonical tag must NOT be in the pending list.
    assert "existing-canonical" not in pending_names


@pytest.mark.asyncio
async def test_commit_new_tag_active_when_auto_approve_on(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """With tags.auto_approve ON, a brand-new import tag lands active, not pending.

    Mirrors ``test_commit_new_tag_created_as_pending`` but flips the setting on
    first — verifying the auto-approve gate (#31) creates the tag ``active`` and
    keeps it out of the admin pending queue.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from app.models.import_session import ImportSession, ImportSessionStatus  # noqa: PLC0415
    from app.models.tag import Tag, TagStatus  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)

    # Enable auto-approve for new tags.
    setting_resp = await client.put(
        "/api/settings/tags.auto_approve",
        json={"value": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert setting_resp.status_code == 200, setting_resp.text

    lib_path = tmp_path / "lib"
    lib_path.mkdir()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Auto Approve Lib", "mount_path": str(lib_path)},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    library_id = lib_resp.json()["id"]

    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    res = await db_session.execute(
        select(ImportSession).where(ImportSession.id == session_id)
    )
    sess = res.scalar_one()
    sess.status = ImportSessionStatus.pending_wizard
    sess.confirmed_title = "Auto Approve Item"
    sess.library_id = library_id
    sess.tag_state = {"confirmed": ["auto-approved-tag"], "pending": []}
    await db_session.flush()

    commit_resp = await client.post(
        f"/api/import-sessions/{session_id}/commit",
        headers={"X-CSRF-Token": csrf},
    )
    assert commit_resp.status_code == 200, commit_resp.text

    res = await db_session.execute(
        select(Tag).where(Tag.name == "auto-approved-tag")
    )
    tag_new = res.scalar_one_or_none()
    assert tag_new is not None, "New tag should be created at commit time"
    assert tag_new.status == TagStatus.active, (
        "With tags.auto_approve ON, a brand-new import tag must land active"
    )

    # It must NOT appear in the admin pending queue.
    pending_resp = await client.get("/api/admin/tags/pending")
    assert pending_resp.status_code == 200
    pending_names = [t["name"] for t in pending_resp.json()]
    assert "auto-approved-tag" not in pending_names


# ---------------------------------------------------------------------------
# URL scraper unit tests (no network; fixture-based)
# ---------------------------------------------------------------------------


def test_scrape_url_extracts_og_metadata() -> None:
    """scrape_url extracts OG title, description, and image from HTML fixture."""
    from app.storage.scraper import scrape_url  # noqa: PLC0415

    html = """<!DOCTYPE html>
<html>
<head>
  <meta property="og:title" content="Awesome 3D Benchy" />
  <meta property="og:description" content="The 3D printing torture test boat." />
  <meta property="og:image" content="https://example.com/benchy.jpg" />
  <meta property="og:site_name" content="Example Site" />
  <meta name="keywords" content="boat, benchy, test" />
</head>
<body><h1>Benchy</h1></body>
</html>"""

    from app.storage.ssrf_guard import GuardedResponse  # noqa: PLC0415

    resp = GuardedResponse(
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=html.encode("utf-8"),
        final_url="https://example.com/thing/123",
    )

    with patch("app.storage.scraper.guarded_fetch", return_value=resp):
        with patch("app.storage.scraper._robots_allows", return_value=True):
            with patch("socket.getaddrinfo", _fake_public_getaddrinfo):
                result = scrape_url("https://example.com/thing/123")

    assert result.title == "Awesome 3D Benchy"
    assert result.description == "The 3D printing torture test boat."
    assert "https://example.com/benchy.jpg" in result.image_urls
    assert result.source_site == "Example Site"
    assert "boat" in result.raw_tags or "benchy" in result.raw_tags


def test_scrape_url_robots_blocked() -> None:
    """scrape_url returns blocked=True when robots.txt disallows the path."""
    from app.storage.scraper import scrape_url  # noqa: PLC0415

    with patch("app.storage.scraper._robots_allows", return_value=False):
        result = scrape_url("https://example.com/thing/123")

    assert result.blocked is True
    assert result.title is None


def test_scrape_url_http_timeout() -> None:
    """scrape_url handles HTTP timeout gracefully."""
    import httpx  # noqa: PLC0415

    from app.storage.scraper import scrape_url  # noqa: PLC0415

    with patch(
        "app.storage.scraper.guarded_fetch",
        side_effect=httpx.TimeoutException("timeout"),
    ):
        with patch("app.storage.scraper._robots_allows", return_value=True):
            with patch("socket.getaddrinfo", _fake_public_getaddrinfo):
                result = scrape_url("https://slow-site.com/thing")

    assert result.blocked is False
    assert result.title is None
    assert result.note is not None
    assert "timeout" in result.note.lower() or "timed out" in result.note.lower()


def test_extract_domain() -> None:
    """extract_domain strips www. prefix."""
    from app.storage.scraper import extract_domain  # noqa: PLC0415

    assert extract_domain("https://www.thingiverse.com/thing:123") == "thingiverse.com"
    assert extract_domain("https://printables.com/model/456") == "printables.com"
    assert extract_domain("https://MAKERWORLD.COM/en/models/1") == "makerworld.com"


# ---------------------------------------------------------------------------
# Image selection: prefer full-res over og:image (issue #28)
# ---------------------------------------------------------------------------


def test_srcset_largest_prefers_widest() -> None:
    """_srcset_largest picks the URL with the largest width descriptor."""
    from app.storage.scraper import _srcset_largest  # noqa: PLC0415

    srcset = (
        "https://cdn.example.com/small.jpg 320w, "
        "https://cdn.example.com/large.jpg 1600w, "
        "https://cdn.example.com/medium.jpg 800w"
    )
    assert _srcset_largest(srcset) == "https://cdn.example.com/large.jpg"


def test_srcset_largest_density_and_bare() -> None:
    """Density descriptors and bare single entries are handled."""
    from app.storage.scraper import _srcset_largest  # noqa: PLC0415

    assert _srcset_largest("https://x/a.jpg 1x, https://x/b.jpg 2x") == "https://x/b.jpg"
    assert _srcset_largest("https://x/solo.jpg") == "https://x/solo.jpg"
    assert _srcset_largest("") is None


def test_extract_images_prefers_srcset_over_og() -> None:
    """A larger srcset candidate beats the downscaled og:image (first/default)."""
    from app.storage.scraper import scrape_url  # noqa: PLC0415
    from app.storage.ssrf_guard import GuardedResponse  # noqa: PLC0415

    html = """<!DOCTYPE html><html><head>
      <meta property="og:title" content="Widget" />
      <meta property="og:image" content="https://cdn.example.com/social-card-1200x630.jpg" />
    </head><body>
      <img src="https://cdn.example.com/thumb.jpg"
           srcset="https://cdn.example.com/w400.jpg 400w,
                   https://cdn.example.com/w2000.jpg 2000w" />
    </body></html>"""

    resp = GuardedResponse(
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=html.encode("utf-8"),
        final_url="https://example.com/thing/1",
    )
    with patch("app.storage.scraper.guarded_fetch", return_value=resp):
        with patch("app.storage.scraper._robots_allows", return_value=True):
            with patch("socket.getaddrinfo", _fake_public_getaddrinfo):
                result = scrape_url("https://example.com/thing/1")

    # Full-res srcset image is first; og:image retained only as a fallback.
    assert result.image_urls[0] == "https://cdn.example.com/w2000.jpg"
    assert "https://cdn.example.com/social-card-1200x630.jpg" in result.image_urls
    assert result.image_urls.index("https://cdn.example.com/w2000.jpg") < result.image_urls.index(
        "https://cdn.example.com/social-card-1200x630.jpg"
    )


def test_extract_images_og_only_fallback() -> None:
    """When no better image exists, og:image is still collected (no regression)."""
    from app.storage.scraper import scrape_url  # noqa: PLC0415
    from app.storage.ssrf_guard import GuardedResponse  # noqa: PLC0415

    html = """<!DOCTYPE html><html><head>
      <meta property="og:title" content="Widget" />
      <meta property="og:image" content="https://cdn.example.com/only.jpg" />
    </head><body><h1>hi</h1></body></html>"""

    resp = GuardedResponse(
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=html.encode("utf-8"),
        final_url="https://example.com/thing/2",
    )
    with patch("app.storage.scraper.guarded_fetch", return_value=resp):
        with patch("app.storage.scraper._robots_allows", return_value=True):
            with patch("socket.getaddrinfo", _fake_public_getaddrinfo):
                result = scrape_url("https://example.com/thing/2")

    assert result.image_urls == ["https://cdn.example.com/only.jpg"]


# ---------------------------------------------------------------------------
# Title / description boilerplate stripping (issue #27)
# ---------------------------------------------------------------------------


def test_clean_title_strips_printables_boilerplate() -> None:
    """The exact Printables title example is stripped to 'by Fuu'."""
    from app.storage.scraper import _clean_title  # noqa: PLC0415

    raw = "NeilMed Sinus Rinse holder by Fuu | Download free STL model | Printables.com"
    assert _clean_title(raw) == "NeilMed Sinus Rinse holder by Fuu"


def test_clean_title_strips_dash_site_suffix() -> None:
    """A trailing ' - <Site>.com' suffix (no pipe) is stripped."""
    from app.storage.scraper import _clean_title  # noqa: PLC0415

    assert _clean_title("Cool Bracket - MakerWorld.com") == "Cool Bracket"
    # No boilerplate → unchanged.
    assert _clean_title("Just A Plain Title") == "Just A Plain Title"


def test_clean_description_strips_boilerplate() -> None:
    """The exact Printables description example stops at the pipe."""
    from app.storage.scraper import _clean_description  # noqa: PLC0415

    raw = (
        "A holder for the bottle which I had trouble finding a place to store. "
        "| Download free 3D printable STL models"
    )
    assert _clean_description(raw) == (
        "A holder for the bottle which I had trouble finding a place to store."
    )


# ---------------------------------------------------------------------------
# Creator extraction from title (issue #27)
# ---------------------------------------------------------------------------


def test_creator_from_title_printables_pattern() -> None:
    """'<name> by <Creator> | ...' yields the creator; non-matching yields None."""
    from app.storage.scraper import _creator_from_title  # noqa: PLC0415

    raw = "NeilMed Sinus Rinse holder by Fuu | Download free STL model | Printables.com"
    assert _creator_from_title(raw) == "Fuu"
    # Already-cleaned title still works.
    assert _creator_from_title("Some Widget by Alice") == "Alice"
    # No " by " → no false positive.
    assert _creator_from_title("Standby Power Monitor") is None
    assert _creator_from_title(None) is None


def test_creator_from_title_flows_into_scrape_result() -> None:
    """scrape_url derives creator_name from the title when no author meta."""
    from app.storage.scraper import scrape_url  # noqa: PLC0415
    from app.storage.ssrf_guard import GuardedResponse  # noqa: PLC0415

    og_title = (
        "NeilMed Sinus Rinse holder by Fuu | Download free STL model | Printables.com"
    )
    html = f"""<!DOCTYPE html><html><head>
      <meta property="og:title" content="{og_title}" />
      <link rel="author" href="https://printables.com/@Fuu_123" />
    </head><body><h1>hi</h1></body></html>"""

    resp = GuardedResponse(
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=html.encode("utf-8"),
        final_url="https://printables.com/model/123",
    )
    with patch("app.storage.scraper.guarded_fetch", return_value=resp):
        with patch("app.storage.scraper._robots_allows", return_value=True):
            with patch("socket.getaddrinfo", _fake_public_getaddrinfo):
                result = scrape_url("https://printables.com/model/123")

    assert result.title == "NeilMed Sinus Rinse holder by Fuu"
    assert result.creator_name == "Fuu"
    assert result.creator_profile_url == "https://printables.com/@Fuu_123"


# ---------------------------------------------------------------------------
# Inbox scan safety (unit)
# ---------------------------------------------------------------------------


def test_infer_role_model_file() -> None:
    """Verify that .stl files get the model role."""
    from app.models.file import FileRole  # noqa: PLC0415
    from app.storage.inventory import infer_role  # noqa: PLC0415

    assert infer_role("model.stl") == FileRole.model
    assert infer_role("thing.3mf") == FileRole.model


def test_infer_role_render() -> None:
    """Verify that files in renders/ get the render role."""
    from app.models.file import FileRole  # noqa: PLC0415
    from app.storage.inventory import infer_role  # noqa: PLC0415

    assert infer_role("renders/abc123.png") == FileRole.render


# ---------------------------------------------------------------------------
# _scraped_image_ext unit tests
# ---------------------------------------------------------------------------


def test_scraped_image_ext_content_type_wins() -> None:
    """Content-Type is preferred over URL suffix for extension detection."""
    from app.routers.import_sessions.sessions import _scraped_image_ext  # noqa: PLC0415

    # MakerWorld CDN URL with no dot in the last segment — Content-Type must win.
    assert _scraped_image_ext(
        "https://cdn.makerworld.com.cn/mkm/cover/image/format,webp",
        "image/webp",
    ) == ".webp"

    assert _scraped_image_ext(
        "https://cdn.makerworld.com.cn/mkm/cover/image/format,webp",
        "image/jpeg",
    ) == ".jpg"

    assert _scraped_image_ext(
        "https://cdn.example.com/img/format,webp",
        "image/png",
    ) == ".png"


def test_scraped_image_ext_fallback_to_url() -> None:
    """URL path suffix is used when Content-Type is missing or unrecognised."""
    from app.routers.import_sessions.sessions import _scraped_image_ext  # noqa: PLC0415

    assert _scraped_image_ext("https://example.com/photo.jpg", "") == ".jpg"
    assert _scraped_image_ext("https://example.com/photo.jpeg", "") == ".jpg"
    assert _scraped_image_ext("https://example.com/photo.png", "text/html") == ".png"
    assert _scraped_image_ext("https://example.com/photo.gif", "") == ".gif"


def test_scraped_image_ext_fallback_to_jpg() -> None:
    """Falls back to .jpg when neither Content-Type nor URL gives a known extension."""
    from app.routers.import_sessions.sessions import _scraped_image_ext  # noqa: PLC0415

    assert _scraped_image_ext("https://cdn.example.com/format,webp", "") == ".jpg"
    assert _scraped_image_ext("https://cdn.example.com/format,webp", "text/html") == ".jpg"
    assert _scraped_image_ext("https://cdn.example.com/thing", "") == ".jpg"


# ---------------------------------------------------------------------------
# Commit: scraped URL images get collision-free filenames
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_scraped_images_unique_filenames(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Committing a session with multiple scraped URLs sharing the same basename
    produces a distinct file on disk and a distinct Image.path for each image.

    Reproduces the MakerWorld CDN pattern where every gallery image URL ends in
    ``image/format,webp`` — prior to the fix all images overwrote the same file.
    """
    import uuid as _uuid  # noqa: PLC0415

    from sqlalchemy import select as _select  # noqa: PLC0415

    from app.models.image import Image  # noqa: PLC0415
    from app.models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionImage,
        ImportSessionStatus,
    )

    csrf = await _setup_and_login(client, tmp_path)

    # Library rooted at a temp dir so the commit can create item directories.
    lib_path = tmp_path / "lib"
    lib_path.mkdir()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Collision Test Lib", "mount_path": str(lib_path)},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    library_id = lib_resp.json()["id"]

    # Create a bare upload session then advance it to pending_wizard in the DB.
    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    session_id = _uuid.UUID(create_resp.json()["id"])

    res = await db_session.execute(
        _select(ImportSession).where(ImportSession.id == session_id)
    )
    sess = res.scalar_one()
    sess.status = ImportSessionStatus.pending_wizard
    sess.confirmed_title = "Collision Test Item"
    sess.library_id = library_id
    await db_session.flush()

    # Two scraped URL images whose URLs share the same basename (``format,webp``).
    img_a = ImportSessionImage(
        session_id=session_id,
        path="https://cdn.makerworld.com/model/123/image/format,webp",
        is_url=True,
        source="scrape",
        order=0,
        is_default=True,
    )
    img_b = ImportSessionImage(
        session_id=session_id,
        path="https://cdn.makerworld.com/model/456/image/format,webp",
        is_url=True,
        source="scrape",
        order=1,
        is_default=False,
    )
    db_session.add(img_a)
    db_session.add(img_b)
    await db_session.flush()

    # Stub the guarded image fetch so both URLs return 200 with webp content-type.
    fake_img_bytes = b"\x00\x00\x00\x0c"  # minimal placeholder bytes

    from app.storage.ssrf_guard import GuardedResponse  # noqa: PLC0415

    def _fake_guarded_fetch(url: str, **kwargs: object) -> GuardedResponse:
        return GuardedResponse(
            status_code=200,
            headers={"content-type": "image/webp"},
            content=fake_img_bytes,
            final_url=url,
        )

    with patch(
        "app.routers.import_sessions.sessions.guarded_fetch", _fake_guarded_fetch
    ):
        commit_resp = await client.post(
            f"/api/import-sessions/{session_id}/commit",
            headers={"X-CSRF-Token": csrf},
        )

    assert commit_resp.status_code == 200, commit_resp.text
    data = commit_resp.json()
    item_id = data["item_id"]

    # Fetch the Image rows written to the DB.
    img_res = await db_session.execute(
        _select(Image).where(Image.item_id == item_id).order_by(Image.order)
    )
    images = img_res.scalars().all()

    assert len(images) == 2, f"Expected 2 Image rows, got {len(images)}"

    paths = [img.path for img in images]
    assert len(set(paths)) == 2, f"Image paths must be distinct; got {paths}"

    # Each file must actually exist on disk and be distinct.
    from app.models.item import Item  # noqa: PLC0415

    item_res = await db_session.execute(_select(Item).where(Item.id == item_id))
    item_row = item_res.scalar_one()
    item_dir_root = Path(item_row.dir_path)

    disk_paths = [item_dir_root / p for p in paths]
    for dp in disk_paths:
        assert dp.exists(), f"Expected file on disk: {dp}"

    assert disk_paths[0] != disk_paths[1], "Files must be at distinct paths on disk"

    # Regression: the scraped image files must ALSO appear in the file list (File rows),
    # not only the thumbnail gallery (Image rows). inventory_item runs before the images
    # are downloaded, so a re-inventory at commit time is required — otherwise the images
    # showed as thumbnails but were missing from the file list until a rescan.
    from app.models.file import File as _FileRow  # noqa: PLC0415

    file_res = await db_session.execute(
        _select(_FileRow).where(_FileRow.item_id == item_id)
    )
    file_paths = {f.path for f in file_res.scalars().all()}
    for p in paths:
        assert p in file_paths, (
            f"scraped image {p!r} missing from the file list (File rows); "
            f"got {sorted(file_paths)}"
        )

    # Commit must enqueue an analyze job (a queued Job row of type 'analyze') — every
    # other create/upload/rescan path does. Without this an imported item with no ZIP
    # was never analyzed until a manual rescan.
    from app.models.job import Job as _JobRow  # noqa: PLC0415

    job_res = await db_session.execute(
        _select(_JobRow).where(_JobRow.item_id == item_id, _JobRow.type == "analyze")
    )
    assert job_res.scalars().first() is not None, (
        "commit did not enqueue an analyze job for the item"
    )
