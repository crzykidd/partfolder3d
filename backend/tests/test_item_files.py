"""Tests for item file management (upload, delete, rename) and extract_archives
Job tracking — issues #18 and #19.

Uses the same ephemeral Postgres + per-test rollback approach as other suites.
The extract_archives Job test uses SessionLocal() directly (the task creates its
own sessions), so it commits and cleans up its own data independently.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File, FileRole
from app.models.job import Job

# ---------------------------------------------------------------------------
# Helpers shared with other test suites
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient, tmp_path: Path) -> str:
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


async def _create_library_and_item(
    client: AsyncClient,
    tmp_path: Path,
    csrf: str,
    item_title: str = "Test Item",
    *,
    db_session: AsyncSession | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a library (with real dir) and an item. Returns (lib_data, item_data).

    Item creation now writes ``queued`` render+analyze Job rows (#20/#30).  Tests
    that assert on their own job set pass ``db_session`` to clear those first.
    """
    mount = str(tmp_path / "library")
    Path(mount).mkdir(parents=True, exist_ok=True)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Test Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201, lib_resp.text
    lib = lib_resp.json()

    item_resp = await client.post(
        "/api/items",
        json={"title": item_title, "library_id": lib["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201, item_resp.text
    item = item_resp.json()

    if db_session is not None:
        from sqlalchemy import delete  # noqa: PLC0415

        from app.models.job import Job  # noqa: PLC0415

        await db_session.execute(delete(Job).where(Job.item_id == item["id"]))
        await db_session.commit()

    return lib, item


# ---------------------------------------------------------------------------
# POST /api/items/{key}/files — upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_creates_row_and_file(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/items/{key}/files creates a File row and writes the file to disk."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]
    item_dir = Path(item["dir_path"])

    stl_bytes = b"solid test\nendsolid"
    resp = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("mymodel.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["path"] == "mymodel.stl"
    assert data["role"] == "model"
    assert data["size"] == len(stl_bytes)

    # Verify DB row
    result = await db_session.execute(
        select(File).where(File.item_id == item["id"], File.path == "mymodel.stl")
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.role == FileRole.model

    # Verify file on disk
    assert (item_dir / "mymodel.stl").exists()


@pytest.mark.asyncio
async def test_upload_file_rejects_unsupported_extension(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """POST /api/items/{key}/files rejects unsupported file types."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]

    resp = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_file_collision_rename(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Uploading a file whose name already exists produces a unique collision name."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]

    stl_bytes = b"solid test\nendsolid"
    # Upload same filename twice
    r1 = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("part.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("part.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["path"] != r1.json()["path"]  # collision resolved


# ---------------------------------------------------------------------------
# DELETE /api/items/{key}/files/{file_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_file_removes_row_and_disk(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE /api/items/{key}/files/{id} removes the DB row and disk file."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]
    item_dir = Path(item["dir_path"])

    # Upload a file
    stl_bytes = b"solid test\nendsolid"
    upload = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("toremove.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["id"]
    file_path = upload.json()["path"]

    # File should exist on disk
    assert (item_dir / file_path).exists()

    # Delete
    del_resp = await client.delete(
        f"/api/items/{item_key}/files/{file_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204, del_resp.text

    # DB row gone
    result = await db_session.execute(select(File).where(File.id == file_id))
    assert result.scalar_one_or_none() is None

    # File gone from disk
    assert not (item_dir / file_path).exists()


@pytest.mark.asyncio
async def test_delete_file_wrong_item_returns_404(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """DELETE with a file_id that belongs to a different item returns 404."""
    csrf = await _setup_and_login(client, tmp_path)
    lib, item1 = await _create_library_and_item(client, tmp_path, csrf, "Item 1")
    # Create item2 in the same library so we don't hit the duplicate mount_path guard.
    item2_resp = await client.post(
        "/api/items",
        json={"title": "Item 2", "library_id": lib["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert item2_resp.status_code == 201
    item2 = item2_resp.json()

    stl_bytes = b"solid\nendsolid"
    upload = await client.post(
        f"/api/items/{item1['key']}/files",
        files={"file": ("model.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload.status_code == 201
    file_id = upload.json()["id"]

    # Try to delete item1's file via item2's endpoint
    resp = await client.delete(
        f"/api/items/{item2['key']}/files/{file_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/items/{key}/files/{file_id} — rename
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rename_file_updates_path_and_disk(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """PATCH /api/items/{key}/files/{id} renames file on disk and in DB."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]
    item_dir = Path(item["dir_path"])

    stl_bytes = b"solid test\nendsolid"
    upload = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("oldname.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["id"]
    old_path = upload.json()["path"]

    rename_resp = await client.patch(
        f"/api/items/{item_key}/files/{file_id}",
        json={"name": "newname.stl"},
        headers={"X-CSRF-Token": csrf},
    )
    assert rename_resp.status_code == 200, rename_resp.text
    data = rename_resp.json()
    assert data["path"] == "newname.stl"
    assert data["role"] == "model"

    # Old file gone, new file present
    assert not (item_dir / old_path).exists()
    assert (item_dir / "newname.stl").exists()

    # DB row updated
    result = await db_session.execute(select(File).where(File.id == file_id))
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.path == "newname.stl"


@pytest.mark.asyncio
async def test_rename_file_rejects_path_traversal(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """Rename with path traversal components is rejected with 422."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]

    stl_bytes = b"solid\nendsolid"
    upload = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("orig.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload.status_code == 201
    file_id = upload.json()["id"]

    for bad_name in ["../evil.stl", "sub/dir.stl", "bad\\name.stl"]:
        resp = await client.patch(
            f"/api/items/{item_key}/files/{file_id}",
            json={"name": bad_name},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422, f"Expected 422 for {bad_name!r}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_rename_file_collision_returns_409(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """Renaming to an existing filename returns 409 Conflict."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]

    stl_bytes = b"solid\nendsolid"
    # Upload two files
    r1 = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("first.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    r2 = await client.post(
        f"/api/items/{item_key}/files",
        files={"file": ("second.stl", io.BytesIO(stl_bytes), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    file1_id = r1.json()["id"]

    # Try to rename first.stl → second.stl (collision)
    resp = await client.patch(
        f"/api/items/{item_key}/files/{file1_id}",
        json={"name": "second.stl"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/items/{key}/jobs — active job listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_item_jobs_empty(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """GET /api/items/{key}/jobs returns [] when no active jobs exist."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(
        client, tmp_path, csrf, db_session=db_session
    )
    item_key = item["key"]

    resp = await client.get(f"/api/items/{item_key}/jobs")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_item_jobs_returns_running(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """GET /api/items/{key}/jobs returns running jobs for the item."""
    from app.worker.job_tracker import create_job  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(
        client, tmp_path, csrf, db_session=db_session
    )
    item_key = item["key"]
    item_id = item["id"]

    # Create a running job via job_tracker (same test session)
    job_id = await create_job(
        db_session,
        "extract_archives",
        payload={"item_id": item_id},
        item_id=item_id,
    )
    await db_session.flush()

    resp = await client.get(f"/api/items/{item_key}/jobs")
    assert resp.status_code == 200, resp.text
    jobs = resp.json()
    assert len(jobs) == 1
    assert jobs[0]["type"] == "extract_archives"
    assert jobs[0]["status"] == "running"
    assert jobs[0]["id"] == str(job_id)


# ---------------------------------------------------------------------------
# extract_archives Job row integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_archives_creates_job_row(tmp_path: Path) -> None:
    """extract_archives creates a Job row with type='extract_archives'.

    This test uses SessionLocal() directly because extract_archives runs its
    own DB sessions (it's an arq task that commits independently of any caller).
    Data is committed and cleaned up explicitly.
    """
    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415
    from app.worker.tasks.archive import extract_archives  # noqa: PLC0415

    # Set up real on-disk library and item dir
    mount = str(tmp_path / "library")
    Path(mount).mkdir(parents=True, exist_ok=True)
    item_dir = tmp_path / "library" / "ab" / "test-ab12cd34"
    item_dir.mkdir(parents=True, exist_ok=True)

    # Create a real ZIP file on disk
    zip_path = item_dir / "archive.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("model.stl", b"solid test\nendsolid")
    zip_path.write_bytes(buf.getvalue())

    # Persist lib + item + file row (committed so the worker task can find them)
    item_id: int
    async with SessionLocal() as db:
        lib = Library(name="IntegLib", mount_path=mount, enabled=True)
        db.add(lib)
        await db.flush()

        item = Item(
            key="ab12cd34",
            title="Test",
            slug="test-ab12cd34",
            library_id=lib.id,
            dir_path=str(item_dir),
            schema_version=1,
        )
        db.add(item)
        await db.flush()

        stat = zip_path.stat()
        f = File(
            item_id=item.id,
            path="archive.zip",
            role=FileRole.zip,
            size=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            last_seen_size=stat.st_size,
            last_seen_mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )
        db.add(f)
        await db.commit()
        item_id = item.id

    try:
        # Run the worker task (ctx={} — no arq job_id)
        await extract_archives({}, item_id)

        # Verify a Job row was created and succeeded
        async with SessionLocal() as db:
            result = await db.execute(
                select(Job).where(
                    Job.type == "extract_archives",
                    Job.item_id == item_id,
                )
            )
            job = result.scalar_one_or_none()
            assert job is not None, "extract_archives must create a Job row"
            assert job.status == "succeeded", f"Expected succeeded, got {job.status!r}"
            assert job.finished_at is not None

    finally:
        # Clean up committed data
        async with SessionLocal() as db:
            result = await db.execute(select(Item).where(Item.id == item_id))
            it = result.scalar_one_or_none()
            if it:
                await db.delete(it)
            await db.commit()
