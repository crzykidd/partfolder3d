"""Manyfold connector — Part 2: API client + worker import path + asset download.

Mirrors test_flaresolverr.py's seam-mock pattern (no real HTTP) and
test_bulk_import.py's ``app.db.SessionLocal`` monkeypatch pattern (the worker's
``process_import_session`` opens its own SessionLocal(); patching it to reuse
the test's ``db_session`` makes ORM rows created via ``db_session``/the HTTP
``client`` fixture visible to the worker call, and vice versa).

Covers:
  - A domain match routes to the Manyfold connector path; scrape_url is NEVER
    called; title/description/creator/license land on the session;
    ALL keyword tags land in tag_state; images/files are staged locally
    (ImportSessionImage is_url=False source="scrape"; ImportSessionFile
    selected=True); a ScraperUsage(provider="manyfold") row is written;
    the session ends in pending_wizard.
  - A non-Manyfold domain still takes the normal scrape path (regression).
  - A Manyfold-domain URL that isn't a model page lands in pending_wizard with
    a clear note instead of a doomed scrape.
  - Deselecting a staged file via PATCH then committing excludes it from the
    item while selected files + local (Manyfold-staged) images commit
    correctly as Image(source=scraped).
  - download_file() refuses to follow a redirect to a private/internal host
    (SSRF re-guard), both as a direct unit test and inside the worker flow
    (one bad file is skipped, not a whole-import failure).
"""

from __future__ import annotations

import ipaddress
import socket
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt
from app.models.image import Image, ImageSource
from app.models.import_session import (
    ImportSession,
    ImportSessionFile,
    ImportSessionImage,
    ImportSessionStatus,
    ImportSourceType,
)
from app.models.manyfold import ManyfoldInstance
from app.models.scraper_usage import ScraperUsage
from app.storage.ssrf_guard import SSRFBlockedError

# ---------------------------------------------------------------------------
# Canned fixtures
# ---------------------------------------------------------------------------

BASE_URL = "https://manyfold.example.com"
DOMAIN = "manyfold.example.com"
MODEL_URL = f"{BASE_URL}/models/abc123"

_FILE_DETAILS: dict[str, dict[str, Any]] = {
    f"{BASE_URL}/files/img1": {
        "filename": "preview.png",
        "encodingFormat": "image/png",
        "contentUrl": f"{BASE_URL}/downloads/img1.png",
        "contentSize": 1234,
    },
    f"{BASE_URL}/files/img2": {
        "filename": "extra.png",
        "encodingFormat": "image/png",
        "contentUrl": f"{BASE_URL}/downloads/img2.png",
        "contentSize": 2345,
    },
    f"{BASE_URL}/files/file1": {
        "filename": "model.stl",
        "encodingFormat": "model/stl",
        "contentUrl": f"{BASE_URL}/downloads/file1.stl",
        "contentSize": 5000,
    },
    f"{BASE_URL}/files/file2": {
        "filename": "model_presupported.stl",
        "encodingFormat": "model/stl",
        "contentUrl": f"{BASE_URL}/downloads/file2.stl",
        "contentSize": 6000,
    },
}

_CREATOR_DETAIL = {f"{BASE_URL}/creators/42": {"name": "Jane Doe", "slug": "jane"}}


def _fake_getaddrinfo(host: str, port: object, *args: Any, **kwargs: Any) -> list:
    """Patch for socket.getaddrinfo (mirrors test_phase5_import.py's pattern).

    ssrf_guard.assert_safe_url runs real DNS resolution on every hop, including
    the initial request — with no network in tests this must be faked. Unlike
    the simpler fixed-IP fake used elsewhere, this one passes an already-literal
    IP straight through (so a redirect target like "169.254.169.254" is still
    correctly evaluated as blocked) and only substitutes a public IP for actual
    hostnames like "manyfold.example.com".
    """
    try:
        ipaddress.ip_address(host)
        resolved = host
    except ValueError:
        resolved = "93.184.216.34"
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved, port or 0))]


def _canned_model_json() -> dict[str, Any]:
    return {
        "name": "Cool Widget",
        "caption": "A cool widget",
        "description": "Long description text.",
        "keywords": ["widget", "gadget"],
        "spdx:license": {"licenseId": "CC-BY-4.0"},
        "sensitive": False,
        "creator": {"@id": f"{BASE_URL}/creators/42"},
        "links": [],
        "preview_file": {"@id": f"{BASE_URL}/files/img1"},
        "hasPart": [
            {"@id": f"{BASE_URL}/files/img1", "name": "preview.png", "@type": "3DModel"},
            {"@id": f"{BASE_URL}/files/img2", "name": "extra.png", "@type": "3DModel"},
            {"@id": f"{BASE_URL}/files/file1", "name": "model.stl", "@type": "3DModel"},
            {
                "@id": f"{BASE_URL}/files/file2",
                "name": "model_presupported.stl",
                "@type": "3DModel",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Auth / instance / session helpers
# ---------------------------------------------------------------------------


async def _admin_setup(client: AsyncClient) -> tuple[str, int]:
    """Initialize instance and log in as admin. Returns (csrf_token, user_id)."""
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
    csrf = client.cookies.get("pf3d_csrf", "")
    return csrf, resp.json()["user_id"]


async def _create_instance(
    db_session: AsyncSession, *, domain: str = DOMAIN, enabled: bool = True
) -> ManyfoldInstance:
    inst = ManyfoldInstance(
        base_url=BASE_URL,
        domain=domain,
        client_id="test-client",
        client_secret_enc=encrypt("test-secret"),
        scopes="public read",
        enabled=enabled,
    )
    db_session.add(inst)
    await db_session.flush()
    return inst


async def _make_url_session(
    db_session: AsyncSession,
    user_id: int,
    *,
    url: str = MODEL_URL,
    status_: ImportSessionStatus = ImportSessionStatus.processing,
) -> ImportSession:
    session_obj = ImportSession(
        id=uuid.uuid4(),
        status=status_,
        source_type=ImportSourceType.url,
        source_url=url,
        created_by_id=user_id,
    )
    db_session.add(session_obj)
    await db_session.flush()
    return session_obj


def _make_session_local_patch(db_session: AsyncSession):
    """Return a patched SessionLocal that yields db_session (see module docstring)."""

    def fake_session_local():
        @asynccontextmanager
        async def _cm():
            yield db_session

        return _cm()

    return fake_session_local


# ---------------------------------------------------------------------------
# Seam installers
# ---------------------------------------------------------------------------


def _install_token_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.storage.manyfold_client as mc

    def fake_token_caller(token_url: str, form: dict, timeout_s: float) -> tuple:
        return (
            200,
            {
                "access_token": "test-token-abc",
                "token_type": "Bearer",
                "expires_in": 7200,
                "scope": "public read",
            },
        )

    mc._clear_token_cache()
    monkeypatch.setattr(mc, "_manyfold_token_caller", fake_token_caller)


def _install_json_seam(
    monkeypatch: pytest.MonkeyPatch, calls: list[str] | None = None
) -> None:
    import app.storage.manyfold_client as mc

    def fake_json_caller(url: str, headers: dict, timeout_s: float) -> tuple:
        if calls is not None:
            calls.append(url)
        if url == MODEL_URL:
            return 200, _canned_model_json()
        if url in _FILE_DETAILS:
            return 200, _FILE_DETAILS[url]
        if url in _CREATOR_DETAIL:
            return 200, _CREATOR_DETAIL[url]
        return 404, {}

    monkeypatch.setattr(mc, "_manyfold_json_caller", fake_json_caller)


def _install_download_seam(
    monkeypatch: pytest.MonkeyPatch,
    *,
    redirect_url: str | None = None,
    redirect_target: str | None = None,
) -> None:
    import app.storage.manyfold_client as mc

    def fake_download_caller(url: str, headers: dict, timeout_s: float) -> tuple:
        if redirect_url is not None and url == redirect_url:
            return 302, {"location": redirect_target}, b""
        body = f"binary-data-for-{url}".encode()
        return 200, {"content-type": "application/octet-stream"}, body

    monkeypatch.setattr(mc, "_manyfold_download_caller", fake_download_caller)


# ---------------------------------------------------------------------------
# 1. Domain match routes to Manyfold; scrape_url never called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manyfold_domain_routes_and_skips_scrape_url(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.db as db_mod
    import app.storage.scraper as scraper_mod
    from app.worker.tasks import import_session as wi

    _csrf, user_id = await _admin_setup(client)
    await _create_instance(db_session)

    _install_token_seam(monkeypatch)
    _install_json_seam(monkeypatch)
    _install_download_seam(monkeypatch)

    def fake_scrape_url(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("scrape_url must not be called for a Manyfold model URL")

    monkeypatch.setattr(scraper_mod, "scrape_url", fake_scrape_url)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    session_obj = await _make_url_session(db_session, user_id)

    with patch("socket.getaddrinfo", _fake_getaddrinfo):
        await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert session_obj.status == ImportSessionStatus.pending_wizard
    assert session_obj.confirmed_title == "Cool Widget"
    assert session_obj.suggested_title == "Cool Widget"
    assert session_obj.description == "A cool widget"
    assert session_obj.license == "CC-BY-4.0"
    assert session_obj.source_site == DOMAIN
    assert session_obj.creator_name == "Jane Doe"
    assert session_obj.creator_source_site == DOMAIN
    assert session_obj.tag_state == {"confirmed": [], "pending": ["widget", "gadget"]}
    assert session_obj.default_image_path is not None
    assert "2 file" in session_obj.scrape_note
    assert "2 image" in session_obj.scrape_note

    imgs_result = await db_session.execute(
        select(ImportSessionImage).where(ImportSessionImage.session_id == session_obj.id)
    )
    imgs = imgs_result.scalars().all()
    assert len(imgs) == 2
    assert all(not img.is_url for img in imgs)
    assert all(img.source == "scrape" for img in imgs)
    assert sum(1 for img in imgs if img.is_default) == 1

    files_result = await db_session.execute(
        select(ImportSessionFile).where(ImportSessionFile.session_id == session_obj.id)
    )
    files = files_result.scalars().all()
    assert len(files) == 2
    assert all(f.selected for f in files)
    assert {f.original_name for f in files} == {"model.stl", "model_presupported.stl"}

    usage_result = await db_session.execute(
        select(ScraperUsage).where(ScraperUsage.provider == "manyfold")
    )
    usage_rows = usage_result.scalars().all()
    assert len(usage_rows) == 1
    assert usage_rows[0].success is True
    assert usage_rows[0].source_url == MODEL_URL


# ---------------------------------------------------------------------------
# 2. Non-Manyfold domain — regression, normal scrape path unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_manyfold_domain_falls_through_to_normal_scrape(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.db as db_mod
    import app.storage.scraper as scraper_mod
    from app.storage.scraper import ScrapeResult
    from app.worker.tasks import import_session as wi

    _csrf, user_id = await _admin_setup(client)
    # A Manyfold instance IS configured, but for a different domain — must not match.
    await _create_instance(db_session, domain="other-manyfold.example.com")

    scrape_calls: list[str] = []

    def fake_scrape_url(url: str, **kwargs: Any) -> ScrapeResult:
        scrape_calls.append(url)
        return ScrapeResult(url=url, domain="example.com", title="Regular Page", blocked=False)

    monkeypatch.setattr(scraper_mod, "scrape_url", fake_scrape_url)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    other_url = "https://example.com/thing/1"
    session_obj = await _make_url_session(db_session, user_id, url=other_url)

    await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert scrape_calls == [other_url]
    assert session_obj.confirmed_title == "Regular Page"
    assert session_obj.status == ImportSessionStatus.pending_wizard


# ---------------------------------------------------------------------------
# 3. Manyfold domain, not a model URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manyfold_domain_non_model_url_sets_note_and_pending_wizard(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.db as db_mod
    import app.storage.scraper as scraper_mod
    from app.worker.tasks import import_session as wi

    _csrf, user_id = await _admin_setup(client)
    await _create_instance(db_session)

    def fake_scrape_url(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("scrape_url must not be called for a recognized Manyfold host")

    monkeypatch.setattr(scraper_mod, "scrape_url", fake_scrape_url)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    session_obj = await _make_url_session(
        db_session, user_id, url=f"{BASE_URL}/collections/some-collection"
    )

    await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert session_obj.status == ImportSessionStatus.pending_wizard
    assert session_obj.scrape_note is not None
    assert "isn't a model URL" in session_obj.scrape_note


# ---------------------------------------------------------------------------
# 4. File selection: PATCH deselect → commit excludes it; local scrape images commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deselected_file_excluded_from_commit_and_scrape_image_commits(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    csrf, user_id = await _admin_setup(client)

    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Test Lib", "mount_path": str(lib_dir)},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201, lib_resp.text
    lib_id = lib_resp.json()["id"]

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    keep_path = staging_dir / "keep.stl"
    keep_path.write_bytes(b"keep-bytes")
    drop_path = staging_dir / "drop.stl"
    drop_path.write_bytes(b"drop-bytes")
    image_path = staging_dir / "cover.png"
    image_path.write_bytes(b"\x89PNGfakebytes")

    session_obj = ImportSession(
        id=uuid.uuid4(),
        status=ImportSessionStatus.pending_wizard,
        source_type=ImportSourceType.url,
        source_url=MODEL_URL,
        confirmed_title="Selection Test Item",
        library_id=lib_id,
        staging_dir=str(staging_dir),
        created_by_id=user_id,
    )
    db_session.add(session_obj)
    await db_session.flush()

    keep_file = ImportSessionFile(
        session_id=session_obj.id,
        staged_path=str(keep_path),
        original_name="keep.stl",
        role="model",
        size=10,
        selected=True,
    )
    drop_file = ImportSessionFile(
        session_id=session_obj.id,
        staged_path=str(drop_path),
        original_name="drop.stl",
        role="model",
        size=10,
        selected=True,
    )
    img_row = ImportSessionImage(
        session_id=session_obj.id,
        path=str(image_path),
        is_url=False,
        source="scrape",
        order=0,
        is_default=True,
    )
    db_session.add_all([keep_file, drop_file, img_row])
    await db_session.flush()

    # Deselect drop_file.
    resp = await client.patch(
        f"/api/import-sessions/{session_obj.id}/files/{drop_file.id}",
        json={"selected": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    files_by_name = {f["original_name"]: f for f in data["files"]}
    assert files_by_name["drop.stl"]["selected"] is False
    assert files_by_name["keep.stl"]["selected"] is True

    commit_resp = await client.post(
        f"/api/import-sessions/{session_obj.id}/commit",
        headers={"X-CSRF-Token": csrf},
    )
    assert commit_resp.status_code == 200, commit_resp.text
    item_id = commit_resp.json()["item_id"]

    on_disk = {p.name for p in lib_dir.rglob("*") if p.is_file()}
    assert "keep.stl" in on_disk
    assert "drop.stl" not in on_disk

    img_result = await db_session.execute(select(Image).where(Image.item_id == item_id))
    committed_images = img_result.scalars().all()
    assert len(committed_images) == 1
    assert committed_images[0].source == ImageSource.scraped


# ---------------------------------------------------------------------------
# 5. Redirect SSRF guard
# ---------------------------------------------------------------------------


def test_download_file_redirect_to_private_host_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import app.storage.manyfold_client as mc

    download_url = f"{BASE_URL}/downloads/file1.stl"

    def fake_download_caller(url: str, headers: dict, timeout_s: float) -> tuple:
        if url == download_url:
            return 302, {"location": "http://169.254.169.254/secret"}, b""
        raise AssertionError(f"unexpected download URL {url}")

    monkeypatch.setattr(mc, "_manyfold_download_caller", fake_download_caller)

    dest = tmp_path / "out.stl"
    with patch("socket.getaddrinfo", _fake_getaddrinfo), pytest.raises(SSRFBlockedError):
        mc.download_file(download_url, "tok", dest, max_bytes=1024)
    assert not dest.exists()


@pytest.mark.asyncio
async def test_manyfold_import_skips_one_ssrf_blocked_file_not_whole_import(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single file whose contentUrl redirects to a private host is skipped —
    it must not fail the whole Manyfold import (best-effort, matches how a
    single broken scraped image is skipped rather than aborting a commit)."""
    import app.db as db_mod
    from app.worker.tasks import import_session as wi

    _csrf, user_id = await _admin_setup(client)
    await _create_instance(db_session)

    _install_token_seam(monkeypatch)
    _install_json_seam(monkeypatch)
    _install_download_seam(
        monkeypatch,
        redirect_url=f"{BASE_URL}/downloads/file2.stl",
        redirect_target="http://169.254.169.254/secret",
    )
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    session_obj = await _make_url_session(db_session, user_id)

    with patch("socket.getaddrinfo", _fake_getaddrinfo):
        await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    # Import still completes successfully — not marked failed.
    assert session_obj.status == ImportSessionStatus.pending_wizard

    files_result = await db_session.execute(
        select(ImportSessionFile).where(ImportSessionFile.session_id == session_obj.id)
    )
    files = files_result.scalars().all()
    # Only the file whose download didn't redirect to a blocked host was staged.
    assert len(files) == 1
    assert files[0].original_name == "model.stl"


# ---------------------------------------------------------------------------
# 6. Internal-URL rewrite + trusted-instance SSRF exemption
#    (both regressions were found by live-testing against a real instance:
#     a reverse-proxied Manyfold serializes internal @id/contentUrl hosts, and
#     a self-hosted instance resolves to a private/LAN IP.)
# ---------------------------------------------------------------------------


def test_rewrite_to_base_swaps_internal_origin() -> None:
    import app.storage.manyfold_client as mc

    # Manyfold behind a reverse proxy emits @id/contentUrl with its INTERNAL host.
    assert (
        mc._rewrite_to_base(BASE_URL, "http://localhost:3214/models/x/model_files/y")
        == f"{BASE_URL}/models/x/model_files/y"
    )
    # Query preserved; None passes through; a relative URL is joined onto base.
    assert (
        mc._rewrite_to_base(BASE_URL, "http://localhost:3214/f?derivative=thumb")
        == f"{BASE_URL}/f?derivative=thumb"
    )
    assert mc._rewrite_to_base(BASE_URL, None) is None
    assert mc._rewrite_to_base(BASE_URL, "/rel/path") == f"{BASE_URL}/rel/path"


def test_fetch_model_rewrites_internal_file_and_creator_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reverse-proxied instance emits @id/contentUrl/preview_file/creator with
    an internal host (localhost:3214). fetch_model must fetch file/creator
    details from — and return content_urls on — the configured public base_url,
    never the internal host (else every file is silently dropped)."""
    import app.storage.manyfold_client as mc

    internal = "http://localhost:3214"
    model_json = {
        "name": "Proxy Model",
        "keywords": ["x"],
        "creator": {"@id": f"{internal}/creators/9"},
        "preview_file": {"@id": f"{internal}/files/imgA"},
        "hasPart": [
            {"@id": f"{internal}/files/imgA", "name": "a.png", "@type": "3DModel"},
        ],
    }
    file_detail = {
        "filename": "a.png",
        "encodingFormat": "image/png",
        "contentUrl": f"{internal}/downloads/a.png",
        "contentSize": 10,
    }
    creator_detail = {"name": "Proxied Creator", "slug": "pc"}

    seen: list[str] = []

    def fake_json_caller(url: str, headers: dict, timeout_s: float) -> tuple:
        seen.append(url)
        if url == MODEL_URL:
            return 200, model_json
        if url == f"{BASE_URL}/files/imgA":
            return 200, file_detail
        if url == f"{BASE_URL}/creators/9":
            return 200, creator_detail
        return 404, {}

    monkeypatch.setattr(mc, "_manyfold_json_caller", fake_json_caller)

    model = mc.fetch_model(BASE_URL, "abc123", "tok")

    # File detail + creator were fetched from the PUBLIC base, never localhost.
    assert f"{BASE_URL}/files/imgA" in seen
    assert f"{BASE_URL}/creators/9" in seen
    assert not any("localhost:3214" in u for u in seen)
    assert len(model.files) == 1
    assert model.files[0].content_url == f"{BASE_URL}/downloads/a.png"
    assert model.preview_file_id == f"{BASE_URL}/files/imgA"
    assert model.creator_name == "Proxied Creator"


def _private_getaddrinfo(host: str, port: object, *args: Any, **kwargs: Any) -> list:
    """Like _fake_getaddrinfo, but a real hostname resolves to a private LAN IP
    (a self-hosted Manyfold instance)."""
    try:
        ipaddress.ip_address(host)
        resolved = host
    except ValueError:
        resolved = "192.168.51.1"
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved, port or 0))]


def test_download_file_trusts_instance_host_on_private_ip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The configured instance host is admin-trusted: a direct download from it
    must NOT be SSRF-blocked even when it resolves to a private/LAN IP (a
    self-hosted instance). Regression for a 192.168.x instance refusing all
    downloads."""
    import app.storage.manyfold_client as mc

    download_url = f"{BASE_URL}/downloads/file1.stl"

    def fake_download_caller(url: str, headers: dict, timeout_s: float) -> tuple:
        assert url == download_url
        return 200, {"content-type": "application/octet-stream"}, b"stlbytes"

    monkeypatch.setattr(mc, "_manyfold_download_caller", fake_download_caller)
    dest = tmp_path / "out.stl"
    with patch("socket.getaddrinfo", _private_getaddrinfo):
        n = mc.download_file(download_url, "tok", dest, max_bytes=1024)
    assert n == len(b"stlbytes")
    assert dest.read_bytes() == b"stlbytes"


def test_download_file_blocks_cross_host_redirect_from_private_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The trust is host-scoped, not blanket: a redirect that LEAVES the trusted
    instance to another private host is still refused."""
    import app.storage.manyfold_client as mc

    download_url = f"{BASE_URL}/downloads/file1.stl"

    def fake_download_caller(url: str, headers: dict, timeout_s: float) -> tuple:
        if url == download_url:
            return 302, {"location": "http://169.254.169.254/secret"}, b""
        raise AssertionError(f"unexpected download URL {url}")

    monkeypatch.setattr(mc, "_manyfold_download_caller", fake_download_caller)
    dest = tmp_path / "out.stl"
    with patch("socket.getaddrinfo", _private_getaddrinfo), pytest.raises(SSRFBlockedError):
        mc.download_file(download_url, "tok", dest, max_bytes=1024)
    assert not dest.exists()


# ---------------------------------------------------------------------------
# 7. Creation-time SSRF exemption for configured Manyfold instances
#    (found via UI live-testing: a private-IP instance was rejected with
#     "URL is not allowed." at POST /api/import-sessions, before the worker ran)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_exempts_manyfold_url_from_ssrf(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A URL on an enabled Manyfold instance is exempt from the creation-time
    SSRF pre-check (a self-hosted instance may resolve to a private/LAN IP),
    while a plain private-IP URL is still rejected."""
    csrf, _uid = await _admin_setup(client)
    await _create_instance(db_session)  # domain manyfold.example.com, enabled

    # Manyfold-instance URL: accepted — the SSRF pre-check is skipped for it.
    ok = await client.post(
        "/api/import-sessions",
        json={"source_type": "url", "source_url": f"{BASE_URL}/models/xyz789"},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["source_url"] == f"{BASE_URL}/models/xyz789"

    # A non-Manyfold private URL is still blocked by the SSRF guard.
    blocked = await client.post(
        "/api/import-sessions",
        json={"source_type": "url", "source_url": "http://192.168.5.5/thing"},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 422
    assert "not allowed" in blocked.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_session_disabled_manyfold_instance_not_exempt(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A DISABLED Manyfold instance grants no SSRF exemption — its URL on a
    private host is still rejected (only enabled instances are trusted)."""
    csrf, _uid = await _admin_setup(client)
    await _create_instance(db_session, domain="192.168.9.9", enabled=False)

    blocked = await client.post(
        "/api/import-sessions",
        json={"source_type": "url", "source_url": "http://192.168.9.9/models/x"},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 422
    assert "not allowed" in blocked.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 8. Staged-filename extension derivation (found via UI live-testing: an
#    instance served display-name filenames with no extension, so the .3mf
#    wasn't recognized as a model and images served as octet-stream)
# ---------------------------------------------------------------------------


def test_ensure_manyfold_ext_derives_from_encoding_format() -> None:
    from app.worker.tasks.import_session import _ensure_manyfold_ext

    # No extension on the name → derive from the MIME type.
    assert _ensure_manyfold_ext("Cool Model", "model/3mf") == "Cool Model.3mf"
    assert _ensure_manyfold_ext("preview 04", "image/webp") == "preview 04.webp"
    assert _ensure_manyfold_ext("part", "model/stl") == "part.stl"
    # MIME with parameters is tolerated.
    assert _ensure_manyfold_ext("clip", "video/mp4; codecs=avc1") == "clip.mp4"
    # A name that already has a sensible suffix is trusted unchanged.
    assert _ensure_manyfold_ext("model.stl", "model/stl") == "model.stl"
    assert _ensure_manyfold_ext("img.PNG", "image/png") == "img.PNG"
    # Unknown/empty MIME and no suffix → left as-is (no guessing).
    assert _ensure_manyfold_ext("mystery", "") == "mystery"
    assert _ensure_manyfold_ext("mystery", "application/x-unknown") == "mystery"
