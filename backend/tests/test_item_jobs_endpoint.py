"""Tests for GET /api/items/{key}/jobs — active + recent-failed job listing.

Covers:
  - Returns active (queued/running) jobs for an item
  - Returns failed (non-archived) jobs for an item including error + progress
  - Does NOT return succeeded or archived jobs
  - Does NOT return jobs for a different item
  - 404 on unknown item key
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Auth + item-creation helpers (matching the pattern in test_phase2_items.py)
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> str:
    """Full setup + login; returns CSRF token."""
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


async def _create_item(
    client: AsyncClient, tmp_path: Path, csrf: str, title: str = "Test Item"
) -> dict:
    """Create a library + item; return the item JSON dict."""
    # Use a unique mount dir per call so multiple items can be created in one test
    import uuid as _uuid  # noqa: PLC0415
    mount = str(tmp_path / f"library-{_uuid.uuid4().hex[:8]}")
    Path(mount).mkdir(parents=True, exist_ok=True)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": f"Test Lib {title}", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201, lib_resp.text
    lib_id = lib_resp.json()["id"]

    item_resp = await client.post(
        "/api/items",
        json={"title": title, "library_id": lib_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201, item_resp.text
    return item_resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_item_jobs_failed_job(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """GET /api/items/{key}/jobs returns a failed analyze_item job with error + progress."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    csrf = await _setup_and_login(client)
    item = await _create_item(client, tmp_path, csrf)
    item_key = item["key"]
    item_id = item["id"]

    # Create a running job for this item, then fail it with an error
    jid = await create_job(
        db_session,
        "analyze_item",
        payload={"item_id": item_id},
        item_id=item_id,
    )
    await db_session.flush()
    await finish_job(db_session, jid, succeeded=False, error="Trimesh failed: bad mesh")
    await db_session.commit()

    resp = await client.get(f"/api/items/{item_key}/jobs")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data) == 1
    job = data[0]
    assert job["type"] == "analyze_item"
    assert job["status"] == "failed"
    assert job["error"] == "Trimesh failed: bad mesh"
    assert isinstance(job["progress"], int)
    assert "id" in job
    assert "created_at" in job


@pytest.mark.asyncio
async def test_list_item_jobs_running_job(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """GET /api/items/{key}/jobs returns a running job with its progress."""
    from app.worker.job_tracker import create_job, update_job_progress  # noqa: PLC0415

    csrf = await _setup_and_login(client)
    item = await _create_item(client, tmp_path, csrf)
    item_key = item["key"]
    item_id = item["id"]

    jid = await create_job(
        db_session,
        "analyze_item",
        payload={"item_id": item_id},
        item_id=item_id,
    )
    await update_job_progress(db_session, jid, 42)
    await db_session.commit()

    resp = await client.get(f"/api/items/{item_key}/jobs")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data) == 1
    job = data[0]
    assert job["type"] == "analyze_item"
    assert job["status"] == "running"
    assert job["progress"] == 42
    assert job["error"] is None


@pytest.mark.asyncio
async def test_list_item_jobs_excludes_succeeded_and_archived(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Succeeded and archived jobs are NOT returned by the endpoint."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415

    from app.models.job import Job  # noqa: PLC0415
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    csrf = await _setup_and_login(client)
    item = await _create_item(client, tmp_path, csrf)
    item_key = item["key"]
    item_id = item["id"]

    # Create a succeeded job
    jid_ok = await create_job(
        db_session, "analyze_item", payload={"item_id": item_id}, item_id=item_id
    )
    await finish_job(db_session, jid_ok, succeeded=True)

    # Create a failed+archived job
    jid_arch = await create_job(
        db_session, "analyze_item", payload={"item_id": item_id}, item_id=item_id
    )
    await finish_job(db_session, jid_arch, succeeded=False, error="old error")
    # Archive it
    result = await db_session.execute(select(Job).where(Job.id == jid_arch))
    archived_job = result.scalar_one()
    archived_job.archived_at = datetime.now(UTC)

    await db_session.commit()

    resp = await client.get(f"/api/items/{item_key}/jobs")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Both the succeeded and archived-failed jobs should be excluded
    assert data == []


@pytest.mark.asyncio
async def test_list_item_jobs_excludes_other_item_jobs(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Jobs for a different item are NOT returned for the queried item."""
    from app.worker.job_tracker import create_job  # noqa: PLC0415

    csrf = await _setup_and_login(client)
    item1 = await _create_item(client, tmp_path, csrf, title="Item One")
    item2 = await _create_item(client, tmp_path, csrf, title="Item Two")
    item1_key = item1["key"]
    item2_id = item2["id"]

    # Create a running job belonging to item2
    await create_job(
        db_session,
        "analyze_item",
        payload={"item_id": item2_id},
        item_id=item2_id,
    )
    await db_session.commit()

    # item1 should have no jobs
    resp = await client.get(f"/api/items/{item1_key}/jobs")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_item_jobs_404_on_unknown_key(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """GET /api/items/unknown/jobs returns 404 when the item key doesn't exist."""
    csrf = await _setup_and_login(client)
    # We need to be logged in for the auth requirement
    _ = csrf

    resp = await client.get("/api/items/no-such-key/jobs")
    assert resp.status_code == 404, resp.text
