"""Tests: mid-wizard file attach for URL import sessions (issue #27).

Covers:
  A. POST /api/import-sessions/{id}/files (relaxed guards)
     - url session in pending_wizard: staging dir lazily created, files attached
     - committed session → 409
     - inbox session → 422
     - upload session in draft still works (regression guard)

  B. DELETE /api/import-sessions/{id}/files/{file_id}
     - removes ImportSessionFile row and staged file from disk
     - 404 on foreign file_id
     - blocked after commit (409)

  C. End-to-end (#27 resolution): commit a url session that had a file attached
     mid-wizard produces File rows on the resulting item.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_session import (  # noqa: E402
    ImportSession,
    ImportSessionFile,
    ImportSessionStatus,
    ImportSourceType,
)

# ---------------------------------------------------------------------------
# Auth + setup helpers
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> tuple[str, int]:
    """Initialize instance, log in as admin. Returns (csrf, user_id)."""
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
    user_id: int = resp.json()["user_id"]
    return csrf, user_id


async def _make_url_session_pending(
    db: AsyncSession,
    user_id: int,
    library_id: int | None = None,
) -> ImportSession:
    """Insert a url session in pending_wizard directly (skips the scrape job)."""
    sess = ImportSession(
        id=uuid.uuid4(),
        status=ImportSessionStatus.pending_wizard,
        source_type=ImportSourceType.url,
        source_url="https://example.com/model",
        confirmed_title="URL Widget",
        library_id=library_id,
        staging_dir=None,
        created_by_id=user_id,
    )
    db.add(sess)
    await db.flush()
    await db.refresh(sess)
    return sess


# ---------------------------------------------------------------------------
# A. Upload endpoint — relaxed guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_to_url_session_pending_wizard_creates_staging_dir(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Uploading to a url/pending_wizard session lazily creates staging_dir and attaches the file.
    """
    csrf, user_id = await _setup_and_login(client)
    sess = await _make_url_session_pending(db_session, user_id)
    assert sess.staging_dir is None

    resp = await client.post(
        f"/api/import-sessions/{sess.id}/files",
        files={"files": ("model.stl", io.BytesIO(b"STL data"), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Response includes the attached file
    assert len(data["files"]) == 1
    assert data["files"][0]["original_name"] == "model.stl"
    assert data["files"][0]["role"] == "model"

    # staging_dir was created on disk and persisted to DB
    assert data["staging_dir"] is not None
    staging = Path(data["staging_dir"])
    assert staging.is_dir()
    assert (staging / "model.stl").exists()

    # ImportSessionFile row exists
    sf_result = await db_session.execute(
        select(ImportSessionFile).where(ImportSessionFile.session_id == sess.id)
    )
    sfs = sf_result.scalars().all()
    assert len(sfs) == 1
    assert sfs[0].original_name == "model.stl"


@pytest.mark.asyncio
async def test_upload_to_committed_session_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Uploading to a committed session returns 409."""
    csrf, user_id = await _setup_and_login(client)
    sess = await _make_url_session_pending(db_session, user_id)
    sess.status = ImportSessionStatus.committed
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{sess.id}/files",
        files={"files": ("a.stl", io.BytesIO(b"x"), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_upload_to_processing_session_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Uploading to a processing session returns 409."""
    csrf, user_id = await _setup_and_login(client)
    sess = await _make_url_session_pending(db_session, user_id)
    sess.status = ImportSessionStatus.processing
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{sess.id}/files",
        files={"files": ("a.stl", io.BytesIO(b"x"), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_upload_to_inbox_session_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Uploading to an inbox session returns 422 (source_type not supported)."""
    csrf, user_id = await _setup_and_login(client)

    inbox_path = tmp_path / "inbox" / "some-item"
    inbox_path.mkdir(parents=True)
    sess = ImportSession(
        id=uuid.uuid4(),
        status=ImportSessionStatus.pending_wizard,
        source_type=ImportSourceType.inbox,
        inbox_folder=str(inbox_path),
        confirmed_title="Inbox Item",
        created_by_id=user_id,
    )
    db_session.add(sess)
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{sess.id}/files",
        files={"files": ("a.stl", io.BytesIO(b"x"), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_to_upload_session_draft_still_works(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Upload-type draft sessions still accept files (regression guard)."""
    csrf, _uid = await _setup_and_login(client)

    # Create upload session via API (starts as draft with staging_dir)
    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/import-sessions/{session_id}/files",
        files={"files": ("widget.stl", io.BytesIO(b"STL"), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["files"]) == 1
    assert data["files"][0]["original_name"] == "widget.stl"


# ---------------------------------------------------------------------------
# B. Delete staged file endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_session_file_removes_row_and_disk_file(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE /{id}/files/{file_id} removes the row and the staged file from disk."""
    csrf, user_id = await _setup_and_login(client)
    sess = await _make_url_session_pending(db_session, user_id)

    # Set up staging dir + add a file row manually
    staging = tmp_path / "staging" / str(uuid.uuid4())
    staging.mkdir(parents=True)
    staged_file = staging / "part.stl"
    staged_file.write_bytes(b"STL")

    sess.staging_dir = str(staging)
    sf = ImportSessionFile(
        session_id=sess.id,
        staged_path=str(staged_file),
        original_name="part.stl",
        role="model",
        size=3,
    )
    db_session.add(sf)
    await db_session.flush()
    await db_session.refresh(sf)
    file_id = sf.id

    resp = await client.delete(
        f"/api/import-sessions/{sess.id}/files/{file_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["files"] == []

    # Row gone from DB
    gone = (
        await db_session.execute(
            select(ImportSessionFile).where(ImportSessionFile.id == file_id)
        )
    ).scalar_one_or_none()
    assert gone is None

    # File removed from disk
    assert not staged_file.exists()


@pytest.mark.asyncio
async def test_delete_session_file_404_on_foreign_id(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE /{id}/files/{file_id} returns 404 when file_id belongs to a different session."""
    csrf, user_id = await _setup_and_login(client)

    sess_a = await _make_url_session_pending(db_session, user_id)
    sess_b = await _make_url_session_pending(db_session, user_id)

    staging = tmp_path / "staging" / str(uuid.uuid4())
    staging.mkdir(parents=True)
    staged_file = staging / "b.stl"
    staged_file.write_bytes(b"x")
    sess_b.staging_dir = str(staging)

    sf_b = ImportSessionFile(
        session_id=sess_b.id,
        staged_path=str(staged_file),
        original_name="b.stl",
        role="model",
        size=1,
    )
    db_session.add(sf_b)
    await db_session.flush()
    await db_session.refresh(sf_b)

    # Try to delete sess_b's file via sess_a's endpoint
    resp = await client.delete(
        f"/api/import-sessions/{sess_a.id}/files/{sf_b.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_file_blocked_after_commit(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE /{id}/files/{file_id} returns 409 when session is committed."""
    csrf, user_id = await _setup_and_login(client)
    sess = await _make_url_session_pending(db_session, user_id)

    staging = tmp_path / "staging" / str(uuid.uuid4())
    staging.mkdir(parents=True)
    staged_file = staging / "c.stl"
    staged_file.write_bytes(b"y")
    sess.staging_dir = str(staging)

    sf = ImportSessionFile(
        session_id=sess.id,
        staged_path=str(staged_file),
        original_name="c.stl",
        role="model",
        size=1,
    )
    db_session.add(sf)
    sess.status = ImportSessionStatus.committed
    await db_session.flush()
    await db_session.refresh(sf)

    resp = await client.delete(
        f"/api/import-sessions/{sess.id}/files/{sf.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# C. End-to-end: commit a url session with a mid-wizard attached file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_url_session_with_attached_file_creates_item_file_rows(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """A url session with a mid-wizard file attach produces File rows on the committed item.

    End-to-end resolution of issue #27.
    """
    from unittest.mock import patch  # noqa: PLC0415

    from app.models.file import File as FileModel  # noqa: PLC0415

    csrf, user_id = await _setup_and_login(client)

    # Create a library
    lib_path = tmp_path / "lib"
    lib_path.mkdir()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "URL Attach Lib", "mount_path": str(lib_path)},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    library_id = lib_resp.json()["id"]

    # Set up a url session already in pending_wizard
    sess = await _make_url_session_pending(db_session, user_id, library_id=library_id)

    # Attach a file via the upload endpoint (lazy staging dir creation)
    with patch("socket.getaddrinfo"):
        resp = await client.post(
            f"/api/import-sessions/{sess.id}/files",
            files={
                "files": (
                    "widget.stl",
                    io.BytesIO(b"solid widget\nendsolid"),
                    "application/octet-stream",
                )
            },
            headers={"X-CSRF-Token": csrf},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["files"]) == 1

    # Commit the session
    commit_resp = await client.post(
        f"/api/import-sessions/{sess.id}/commit",
        headers={"X-CSRF-Token": csrf},
    )
    assert commit_resp.status_code == 200, commit_resp.text
    item_id: int = commit_resp.json()["item_id"]

    # Verify File rows were created for the attached model file
    file_rows = (
        await db_session.execute(
            select(FileModel).where(FileModel.item_id == item_id)
        )
    ).scalars().all()
    file_names = [f.path for f in file_rows]
    assert any("widget.stl" in p for p in file_names), (
        f"Expected 'widget.stl' in item file paths; got: {file_names}"
    )
