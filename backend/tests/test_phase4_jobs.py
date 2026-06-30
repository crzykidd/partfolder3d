"""Phase 4 tests: Job model, job tracker, jobs API, scheduled-jobs API.

Uses the same ephemeral Postgres + per-test rollback approach as Phase 2/3 tests.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.scheduled_job import ScheduledJob

# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# Job tracker helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_create_and_finish(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job tracker: create → running, finish → succeeded."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    job_id = await create_job(db_session, "render", payload={"item_id": 99})
    await db_session.flush()

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    assert job is not None
    assert job.type == "render"
    assert job.status == "running"
    assert job.progress == 0
    assert job.started_at is not None
    assert job.finished_at is None

    await finish_job(db_session, job_id, succeeded=True, log_text="all good")
    await db_session.flush()

    result2 = await db_session.execute(select(Job).where(Job.id == job_id))
    job2 = result2.scalar_one()
    assert job2.status == "succeeded"
    assert job2.progress == 100
    assert job2.finished_at is not None
    assert job2.log == "all good"


@pytest.mark.asyncio
async def test_job_finish_failed(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job tracker: failed job records its error message."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={})
    await db_session.flush()

    await finish_job(db_session, jid, succeeded=False, error="no backend")
    await db_session.flush()

    result = await db_session.execute(select(Job).where(Job.id == jid))
    job = result.scalar_one()
    assert job.status == "failed"
    assert job.error == "no backend"


@pytest.mark.asyncio
async def test_job_progress_update(client: AsyncClient, db_session: AsyncSession) -> None:
    """update_job_progress clamps to 0–100 and appends log lines."""
    from app.worker.job_tracker import create_job, update_job_progress  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={})
    await db_session.flush()

    await update_job_progress(db_session, jid, 50, log_line="halfway")
    await db_session.flush()

    result = await db_session.execute(select(Job).where(Job.id == jid))
    job = result.scalar_one()
    assert job.progress == 50
    assert "halfway" in (job.log or "")

    # Clamp > 100
    await update_job_progress(db_session, jid, 200)
    await db_session.flush()
    result2 = await db_session.execute(select(Job).where(Job.id == jid))
    assert result2.scalar_one().progress == 100


# ---------------------------------------------------------------------------
# Jobs API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jobs_api_requires_admin(client: AsyncClient) -> None:
    """GET /api/jobs is admin-only; unauthenticated → 401."""
    resp = await client.get("/api/jobs")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jobs_list(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Admin can list jobs; filter by status works."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    j1 = await create_job(db_session, "render", payload={"item_id": 1})
    j2 = await create_job(db_session, "zip_bundle", payload={"bundle_id": "abc"})
    await finish_job(db_session, j1, succeeded=True)
    await db_session.commit()

    await _setup_and_login(client, tmp_path)

    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    ids = [j["id"] for j in body["jobs"]]
    assert str(j1) in ids
    assert str(j2) in ids

    # filter by status=running (j2 is still running)
    resp2 = await client.get("/api/jobs?status=running")
    assert resp2.status_code == 200
    for j in resp2.json()["jobs"]:
        assert j["status"] == "running"


@pytest.mark.asyncio
async def test_get_job(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """GET /api/jobs/{id} returns job detail."""
    from app.worker.job_tracker import create_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={"item_id": 7})
    await db_session.commit()

    await _setup_and_login(client, tmp_path)

    resp = await client.get(f"/api/jobs/{jid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(jid)
    assert body["type"] == "render"
    assert body["payload"]["item_id"] == 7


@pytest.mark.asyncio
async def test_get_job_invalid_uuid(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/jobs/not-a-uuid returns 422."""
    await _setup_and_login(client, tmp_path)
    resp = await client.get("/api/jobs/not-a-uuid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/jobs/{unknown_uuid} returns 404."""
    await _setup_and_login(client, tmp_path)
    resp = await client.get(f"/api/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Scheduled-jobs API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduled_jobs_list(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """GET /api/scheduled-jobs returns seeded rows."""
    sj = ScheduledJob(
        name="test_cleanup",
        description="A test scheduled job",
        schedule="daily at 00:00 UTC",
    )
    db_session.add(sj)
    await db_session.commit()

    await _setup_and_login(client, tmp_path)

    resp = await client.get("/api/scheduled-jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    names = [j["name"] for j in jobs]
    assert "test_cleanup" in names

    tj = next(j for j in jobs if j["name"] == "test_cleanup")
    assert tj["description"] == "A test scheduled job"
    assert tj["is_running"] is False
    assert tj["last_run_at"] is None


@pytest.mark.asyncio
async def test_run_now_not_found(client: AsyncClient, tmp_path: Path) -> None:
    """POST /api/scheduled-jobs/{unknown}/run returns 404."""
    csrf = await _setup_and_login(client, tmp_path)
    resp = await client.post(
        "/api/scheduled-jobs/no_such_job/run",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# render_mesh unit tests (no rendering, just the module API)
# ---------------------------------------------------------------------------


def test_render_mesh_unsupported_extension(tmp_path: Path) -> None:
    """render_mesh_file raises RenderError for non-mesh file types."""
    from app.worker.render_mesh import RenderError, render_mesh_file  # noqa: PLC0415

    fake = tmp_path / "model.blend"
    fake.write_bytes(b"fake blender data")
    with pytest.raises(RenderError, match="Unsupported file type"):
        render_mesh_file(fake)


def test_render_mesh_backend_detection() -> None:
    """get_backend() returns a valid backend string (any of the known values)."""
    from app.worker.render_mesh import get_backend  # noqa: PLC0415

    b = get_backend()
    assert b in ("egl", "osmesa", "vtk", "none")


def test_worker_settings_builds_a_worker() -> None:
    """Regression: `python worker.py` crashed with "'type' object is not
    iterable" because main() called Worker(WorkerSettings) — arq's Worker takes
    `functions` (a list) as its first positional arg, not the settings class.
    create_worker() reads the settings class and must build the worker, with all
    registered task functions and cron jobs resolving."""
    from arq.worker import create_worker  # noqa: PLC0415

    import worker as worker_module  # noqa: PLC0415

    w = create_worker(worker_module.WorkerSettings)  # type: ignore[arg-type]

    # Every Phase 4–6 task is registered…
    for fn in ("render_item", "build_zip_bundle", "exec_scheduled_job",
               "process_import_session", "apply_review_item"):
        assert fn in w.functions, f"task {fn!r} not registered on the worker"
    # …and the recurring cron jobs are wired in.
    assert any(name.startswith("cron:") for name in w.functions)


# ---------------------------------------------------------------------------
# Retry endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_failed_render_job(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: object,
) -> None:
    """POST /api/jobs/{id}/retry on a failed render job re-enqueues render_item."""
    from unittest.mock import AsyncMock, patch  # noqa: PLC0415

    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    # Create a failed render job with item_id in payload.
    # item_id=None for the FK column (no real Item row needed); the payload
    # is what the retry endpoint reads for re-enqueueing.
    jid = await create_job(db_session, "render", payload={"item_id": 42}, item_id=None)
    await finish_job(db_session, jid, succeeded=False, error="render backend unavailable")
    await db_session.commit()

    await _setup_and_login(client, tmp_path)  # type: ignore[arg-type]
    csrf = client.cookies.get("pf3d_csrf", "")

    # Patch the Redis pool so no real Redis connection is needed.
    # create_pool is lazily imported inside the endpoint body, so patch it
    # at the arq module where it lives.
    mock_redis = AsyncMock()
    mock_pool = AsyncMock(return_value=mock_redis)

    with patch("arq.create_pool", mock_pool):
        resp = await client.post(
            f"/api/jobs/{jid}/retry",
            headers={"X-CSRF-Token": csrf},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["queued"] is True

    # Verify that enqueue_job was called with the correct task, item_id, and retry link
    mock_redis.enqueue_job.assert_called_once_with("render_item", 42, retry_of_job_id=str(jid))


@pytest.mark.asyncio
async def test_retry_non_failed_job_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: object,
) -> None:
    """POST /api/jobs/{id}/retry on a running job returns 409."""
    from app.worker.job_tracker import create_job  # noqa: PLC0415

    # create_job sets status = "running"
    jid = await create_job(db_session, "render", payload={"item_id": 5})
    await db_session.commit()

    await _setup_and_login(client, tmp_path)  # type: ignore[arg-type]
    csrf = client.cookies.get("pf3d_csrf", "")

    resp = await client.post(
        f"/api/jobs/{jid}/retry",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409, resp.text
    assert "running" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_retry_succeeded_job_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: object,
) -> None:
    """POST /api/jobs/{id}/retry on a succeeded job returns 409."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={"item_id": 3})
    await finish_job(db_session, jid, succeeded=True)
    await db_session.commit()

    await _setup_and_login(client, tmp_path)  # type: ignore[arg-type]
    csrf = client.cookies.get("pf3d_csrf", "")

    resp = await client.post(
        f"/api/jobs/{jid}/retry",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_retry_non_retriable_type_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: object,
) -> None:
    """POST /api/jobs/{id}/retry on an unknown type returns 400."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    jid = await create_job(db_session, "unknown_type", payload={})
    await finish_job(db_session, jid, succeeded=False, error="oops")
    await db_session.commit()

    await _setup_and_login(client, tmp_path)  # type: ignore[arg-type]
    csrf = client.cookies.get("pf3d_csrf", "")

    resp = await client.post(
        f"/api/jobs/{jid}/retry",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 400, resp.text
    assert "cannot be retried" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_retry_missing_job_returns_404(
    client: AsyncClient,
    tmp_path: object,
) -> None:
    """POST /api/jobs/{unknown_uuid}/retry returns 404."""
    await _setup_and_login(client, tmp_path)  # type: ignore[arg-type]
    csrf = client.cookies.get("pf3d_csrf", "")

    resp = await client.post(
        f"/api/jobs/{uuid.uuid4()}/retry",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404, resp.text
