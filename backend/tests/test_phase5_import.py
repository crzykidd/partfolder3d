"""Phase 5 tests: import sessions, tag reconciliation, site capabilities, tag approval.

Uses the same ephemeral Postgres + per-test rollback approach as earlier phases.
Scrape-related tests use local fixtures — no real network calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site_capability import SiteToken
from app.models.tag import Tag, TagAlias, TagStatus

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

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}
    mock_response.text = html

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(return_value=mock_response)

    with patch("app.storage.scraper.httpx.Client", return_value=mock_client):
        with patch("app.storage.scraper._robots_allows", return_value=True):
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

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("app.storage.scraper.httpx.Client", return_value=mock_client):
        with patch("app.storage.scraper._robots_allows", return_value=True):
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
