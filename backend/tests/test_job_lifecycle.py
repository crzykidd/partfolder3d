"""Job lifecycle tests: cancel, supersede, archive, retention.

All render calls and arq interactions are mocked — no real renders, no Redis.
Uses the same ephemeral Postgres + per-test rollback approach as other suites.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job

# ---------------------------------------------------------------------------
# Shared helpers
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
# §3 — finish_job is a no-op on already-terminal rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_sets_cancelled_and_finish_job_is_noop(
    db_session: AsyncSession,
) -> None:
    """finish_job must not clobber 'cancelled' — the terminal guard must be effective."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    # Create a running job
    jid = await create_job(db_session, "render", payload={"item_id": 99}, item_id=None)
    await db_session.flush()

    result = await db_session.execute(select(Job).where(Job.id == jid))
    job = result.scalar_one()
    assert job.status == "running"

    # Simulate the cancel endpoint: set status directly (as the endpoint does)
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    await db_session.flush()

    # Now simulate the arq BaseException handler calling finish_job(failed)
    await finish_job(db_session, jid, succeeded=False, error="worker cancelled")
    await db_session.flush()

    # The row must still be 'cancelled' — finish_job must be a no-op
    result2 = await db_session.execute(select(Job).where(Job.id == jid))
    job2 = result2.scalar_one()
    assert job2.status == "cancelled", "finish_job clobbered 'cancelled' — terminal guard failed"
    assert job2.error is None, "error should not have been written to a cancelled job"


@pytest.mark.asyncio
async def test_finish_job_noop_on_succeeded(db_session: AsyncSession) -> None:
    """finish_job must not overwrite an already-succeeded row."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={})
    await db_session.flush()

    await finish_job(db_session, jid, succeeded=True)
    await db_session.flush()

    # Second call with failed must not downgrade
    await finish_job(db_session, jid, succeeded=False, error="spurious failure")
    await db_session.flush()

    result = await db_session.execute(select(Job).where(Job.id == jid))
    job = result.scalar_one()
    assert job.status == "succeeded"
    assert job.error is None


# ---------------------------------------------------------------------------
# §5 — retry links retry_of_job_id + supersede-on-success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_links_job_and_supersedes_ancestor_chain(
    db_session: AsyncSession,
) -> None:
    """When a retry succeeds, finish_job must mark the full ancestor chain superseded."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    # Original failed job (no ancestor)
    ancestor_id = await create_job(db_session, "render", payload={"item_id": 1})
    await db_session.flush()

    # Mark original as failed
    await finish_job(db_session, ancestor_id, succeeded=False, error="render error")
    await db_session.flush()

    # First retry job, linked to original
    retry1_id = await create_job(
        db_session, "render", payload={"item_id": 1},
        retry_of_job_id=ancestor_id,
    )
    await db_session.flush()

    # First retry also fails
    await finish_job(db_session, retry1_id, succeeded=False, error="still broken")
    await db_session.flush()

    # Second retry, linked to retry1
    retry2_id = await create_job(
        db_session, "render", payload={"item_id": 1},
        retry_of_job_id=retry1_id,
    )
    await db_session.flush()

    # Second retry succeeds — should supersede retry1 and ancestor
    await finish_job(db_session, retry2_id, succeeded=True)
    await db_session.flush()

    # Check final states
    res_ancestor = await db_session.execute(select(Job).where(Job.id == ancestor_id))
    assert res_ancestor.scalar_one().status == "superseded"

    res_retry1 = await db_session.execute(select(Job).where(Job.id == retry1_id))
    assert res_retry1.scalar_one().status == "superseded"

    res_retry2 = await db_session.execute(select(Job).where(Job.id == retry2_id))
    assert res_retry2.scalar_one().status == "succeeded"


@pytest.mark.asyncio
async def test_retry_endpoint_passes_retry_of_job_id(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/{id}/retry enqueues with retry_of_job_id=str(job.id)."""
    from unittest.mock import AsyncMock, patch  # noqa: PLC0415

    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={"item_id": 77}, item_id=None)
    await finish_job(db_session, jid, succeeded=False, error="broken")
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    mock_redis = AsyncMock()
    mock_pool = AsyncMock(return_value=mock_redis)

    with patch("arq.create_pool", mock_pool):
        resp = await client.post(
            f"/api/jobs/{jid}/retry",
            headers={"X-CSRF-Token": csrf},
        )

    assert resp.status_code == 202, resp.text
    mock_redis.enqueue_job.assert_called_once_with(
        "render_item", 77, retry_of_job_id=str(jid)
    )


# ---------------------------------------------------------------------------
# §4 — cancel endpoint (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_running_job_via_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/{id}/cancel sets status='cancelled' on a running job."""
    from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415

    from app.worker.job_tracker import create_job  # noqa: PLC0415

    jid = await create_job(
        db_session, "render", payload={"item_id": 5},
        arq_job_id="arq:test-job-123",
    )
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    # Patch arq imports — no real Redis in tests
    mock_redis = AsyncMock()
    mock_pool = AsyncMock(return_value=mock_redis)
    mock_arq_job = MagicMock()
    mock_arq_job.abort = AsyncMock(return_value=True)

    with (
        patch("arq.create_pool", mock_pool),
        patch("arq.jobs.Job", return_value=mock_arq_job),
    ):
        resp = await client.post(
            f"/api/jobs/{jid}/cancel",
            headers={"X-CSRF-Token": csrf},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["finished_at"] is not None


@pytest.mark.asyncio
async def test_cancel_non_running_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/{id}/cancel on a non-running job returns 409."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={"item_id": 3})
    await finish_job(db_session, jid, succeeded=True)
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.post(
        f"/api/jobs/{jid}/cancel",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# §6 — clear-by-status + archive + delete + list filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_jobs_by_status_succeeded(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/clear?status=succeeded archives all non-archived succeeded jobs only."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    j1 = await create_job(db_session, "render", payload={"item_id": 10})
    j2 = await create_job(db_session, "render", payload={"item_id": 11})
    j_fail = await create_job(db_session, "render", payload={"item_id": 12})
    await finish_job(db_session, j1, succeeded=True)
    await finish_job(db_session, j2, succeeded=True)
    await finish_job(db_session, j_fail, succeeded=False, error="oops")
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.post(
        "/api/jobs/clear?status=succeeded",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # >= 2 (not == 2): other tests in the same xdist worker DB may leave committed
    # succeeded Job rows (e.g. extract_archives), which this global clear correctly
    # archives too. The per-job assertions below prove OUR jobs were handled right.
    assert body["archived"] >= 2, f"expected >=2 succeeded archived, got {body['archived']}"

    # Succeeded jobs must be archived; failed job must not be touched
    for jid in (j1, j2):
        res = await db_session.execute(select(Job).where(Job.id == jid))
        assert res.scalar_one().archived_at is not None, f"succeeded job {jid} must be archived"

    res_fail = await db_session.execute(select(Job).where(Job.id == j_fail))
    assert res_fail.scalar_one().archived_at is None, "failed job must not be archived"


@pytest.mark.asyncio
async def test_clear_jobs_by_status_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/clear?status=failed archives only failed jobs, leaves succeeded alone."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    j_fail1 = await create_job(db_session, "render", payload={"item_id": 13})
    j_fail2 = await create_job(db_session, "render", payload={"item_id": 14})
    j_ok = await create_job(db_session, "render", payload={"item_id": 15})
    await finish_job(db_session, j_fail1, succeeded=False, error="err1")
    await finish_job(db_session, j_fail2, succeeded=False, error="err2")
    await finish_job(db_session, j_ok, succeeded=True)
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.post(
        "/api/jobs/clear?status=failed",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # >= 2 (not == 2): see the succeeded variant — leaked committed Job rows from
    # other tests inflate the global count; per-job assertions below are the guarantee.
    assert body["archived"] >= 2, f"expected >=2 failed archived, got {body['archived']}"

    for jid in (j_fail1, j_fail2):
        res = await db_session.execute(select(Job).where(Job.id == jid))
        assert res.scalar_one().archived_at is not None, f"failed job {jid} must be archived"

    res_ok = await db_session.execute(select(Job).where(Job.id == j_ok))
    assert res_ok.scalar_one().archived_at is None, (
        "succeeded job must not be archived by failed clear"
    )


@pytest.mark.asyncio
async def test_clear_jobs_by_status_cancelled(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/clear?status=cancelled archives only cancelled jobs."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    j_cancel1 = await create_job(db_session, "render", payload={"item_id": 16})
    j_cancel2 = await create_job(db_session, "render", payload={"item_id": 17})
    j_fail = await create_job(db_session, "render", payload={"item_id": 18})
    await db_session.flush()

    # Simulate cancel (same pattern as the cancel endpoint)
    for jid in (j_cancel1, j_cancel2):
        res = await db_session.execute(select(Job).where(Job.id == jid))
        row = res.scalar_one()
        row.status = "cancelled"
        row.finished_at = datetime.now(UTC)
    await finish_job(db_session, j_fail, succeeded=False, error="err")
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.post(
        "/api/jobs/clear?status=cancelled",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # >= 2 (not == 2): see the succeeded variant — leaked committed Job rows from
    # other tests inflate the global count; per-job assertions below are the guarantee.
    assert body["archived"] >= 2, f"expected >=2 cancelled archived, got {body['archived']}"

    for jid in (j_cancel1, j_cancel2):
        res = await db_session.execute(select(Job).where(Job.id == jid))
        assert res.scalar_one().archived_at is not None, f"cancelled job {jid} must be archived"

    res_fail = await db_session.execute(select(Job).where(Job.id == j_fail))
    assert res_fail.scalar_one().archived_at is None, (
        "failed job must not be archived by cancelled clear"
    )


@pytest.mark.asyncio
async def test_clear_non_archivable_status_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/clear?status=<non-archivable> returns 422 for running and queued."""
    csrf = await _setup_and_login(client, tmp_path)

    for bad_status in ("running", "queued"):
        resp = await client.post(
            f"/api/jobs/clear?status={bad_status}",
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422, (
            f"expected 422 for status={bad_status!r}, got {resp.status_code}: {resp.text}"
        )


@pytest.mark.asyncio
async def test_default_list_excludes_archived_and_superseded(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """GET /api/jobs default view excludes archived and superseded rows."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    # Normal running job — should appear in default list
    j_running = await create_job(db_session, "render", payload={"item_id": 20})
    await db_session.flush()

    # Superseded job (simulate: create failed, create retry, succeed retry)
    j_old = await create_job(db_session, "render", payload={"item_id": 21})
    await db_session.flush()
    await finish_job(db_session, j_old, succeeded=False, error="err")
    await db_session.flush()
    j_new = await create_job(
        db_session, "render", payload={"item_id": 21}, retry_of_job_id=j_old
    )
    await db_session.flush()
    await finish_job(db_session, j_new, succeeded=True)
    await db_session.flush()

    # Archived job
    j_arch = await create_job(db_session, "render", payload={"item_id": 22})
    await finish_job(db_session, j_arch, succeeded=True)
    await db_session.flush()
    res_arch = await db_session.execute(select(Job).where(Job.id == j_arch))
    res_arch.scalar_one().archived_at = datetime.now(UTC)
    await db_session.flush()

    await db_session.commit()

    await _setup_and_login(client, tmp_path)

    # --- Default list ---
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    ids = [j["id"] for j in resp.json()["jobs"]]
    assert str(j_running) in ids, "running job should appear in default list"
    assert str(j_new) in ids, "successful retry should appear in default list"
    assert str(j_old) not in ids, "superseded job should be excluded from default list"
    assert str(j_arch) not in ids, "archived job should be excluded from default list"

    # --- archived=true returns only archived rows ---
    resp_arch = await client.get("/api/jobs?archived=true")
    assert resp_arch.status_code == 200
    arch_ids = [j["id"] for j in resp_arch.json()["jobs"]]
    assert str(j_arch) in arch_ids
    assert str(j_running) not in arch_ids
    assert str(j_old) not in arch_ids  # superseded but not archived

    # --- include_superseded=true reveals superseded rows ---
    resp_sup = await client.get("/api/jobs?include_superseded=true")
    assert resp_sup.status_code == 200
    sup_ids = [j["id"] for j in resp_sup.json()["jobs"]]
    assert str(j_old) in sup_ids, "superseded job should appear with include_superseded=true"
    assert str(j_arch) not in sup_ids, "archived job still excluded even with include_superseded"


@pytest.mark.asyncio
async def test_archive_one_terminal_job(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/{id}/archive sets archived_at on a terminal job."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={"item_id": 30})
    await finish_job(db_session, jid, succeeded=False, error="failed")
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.post(
        f"/api/jobs/{jid}/archive",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["archived_at"] is not None


@pytest.mark.asyncio
async def test_archive_running_job_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/jobs/{id}/archive on a running job returns 409."""
    from app.worker.job_tracker import create_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={"item_id": 31})
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.post(
        f"/api/jobs/{jid}/archive",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_delete_job(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE /api/jobs/{id} hard-deletes the row (204)."""
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    jid = await create_job(db_session, "render", payload={"item_id": 40})
    await finish_job(db_session, jid, succeeded=True)
    await db_session.commit()

    csrf = await _setup_and_login(client, tmp_path)

    resp = await client.delete(
        f"/api/jobs/{jid}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204, resp.text

    # Confirm it's gone
    res = await db_session.execute(select(Job).where(Job.id == jid))
    assert res.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# §7 — Retention cron
# ---------------------------------------------------------------------------
#
# NOTE: _job_history_retention_core opens its own SessionLocal() connection.
# The test fixture wraps everything in an outer rolled-back transaction, so
# committed data is NOT visible cross-connection.  We test the identical DELETE
# query logic directly on db_session instead — this exercises the same SQL
# while staying within the single-connection fixture.


@pytest.mark.asyncio
async def test_retention_deletes_old_succeeded_and_failed_jobs(
    db_session: AsyncSession,
) -> None:
    """Retention DELETE query removes old jobs and keeps recent/running ones."""
    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.worker.job_tracker import create_job, finish_job  # noqa: PLC0415

    now = datetime.now(UTC)
    succeeded_cutoff = now - timedelta(days=settings.JOB_RETENTION_SUCCEEDED_DAYS)
    failed_cutoff = now - timedelta(days=settings.JOB_RETENTION_FAILED_DAYS)

    # Old succeeded job (finished 10 days ago — past 7-day window)
    old_succeeded = await create_job(db_session, "render", payload={"item_id": 50})
    await db_session.flush()
    await finish_job(db_session, old_succeeded, succeeded=True)
    await db_session.flush()
    res = await db_session.execute(select(Job).where(Job.id == old_succeeded))
    res.scalar_one().finished_at = now - timedelta(days=10)
    await db_session.flush()

    # Old failed job (finished 35 days ago — past 30-day window)
    old_failed = await create_job(db_session, "render", payload={"item_id": 51})
    await db_session.flush()
    await finish_job(db_session, old_failed, succeeded=False, error="old error")
    await db_session.flush()
    res2 = await db_session.execute(select(Job).where(Job.id == old_failed))
    res2.scalar_one().finished_at = now - timedelta(days=35)
    await db_session.flush()

    # Recent succeeded job (finished ~now — within 7-day window, keep)
    recent_succeeded = await create_job(db_session, "render", payload={"item_id": 52})
    await db_session.flush()
    await finish_job(db_session, recent_succeeded, succeeded=True)
    await db_session.flush()

    # Running job (no finished_at — must never be touched)
    running_job = await create_job(db_session, "render", payload={"item_id": 53})
    await db_session.flush()

    # Execute the same DELETE query that _job_history_retention_core uses
    result = await db_session.execute(
        sa.delete(Job)
        .where(
            sa.or_(
                sa.and_(Job.status == "succeeded", Job.finished_at < succeeded_cutoff),
                sa.and_(
                    Job.status.in_(["failed", "cancelled", "superseded"]),
                    Job.finished_at < failed_cutoff,
                ),
            )
        )
        .returning(Job.id)
    )
    deleted_ids = {row[0] for row in result.all()}
    await db_session.flush()

    assert old_succeeded in deleted_ids, "old succeeded job should be deleted"
    assert old_failed in deleted_ids, "old failed job should be deleted"
    assert recent_succeeded not in deleted_ids, "recent succeeded job should be kept"
    assert running_job not in deleted_ids, "running job (no finished_at) should be kept"

    # Verify rows actually gone / still present
    for kept_id in (recent_succeeded, running_job):
        r = await db_session.execute(select(Job).where(Job.id == kept_id))
        assert r.scalar_one_or_none() is not None, f"job {kept_id} must still exist"

    for gone_id in (old_succeeded, old_failed):
        r = await db_session.execute(select(Job).where(Job.id == gone_id))
        assert r.scalar_one_or_none() is None, f"job {gone_id} must have been deleted"


@pytest.mark.asyncio
async def test_retention_old_cancelled_superseded_deleted(
    db_session: AsyncSession,
) -> None:
    """Retention DELETE query also removes old cancelled and superseded jobs."""
    import sqlalchemy as sa  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.worker.job_tracker import create_job  # noqa: PLC0415

    now = datetime.now(UTC)
    old_ts = now - timedelta(days=35)
    failed_cutoff = now - timedelta(days=settings.JOB_RETENTION_FAILED_DAYS)

    # Old cancelled job
    j_cancelled = await create_job(db_session, "render", payload={"item_id": 60})
    await db_session.flush()
    j_row = (await db_session.execute(select(Job).where(Job.id == j_cancelled))).scalar_one()
    j_row.status = "cancelled"
    j_row.finished_at = old_ts
    await db_session.flush()

    # Old superseded job
    j_superseded = await create_job(db_session, "render", payload={"item_id": 61})
    await db_session.flush()
    j_row2 = (await db_session.execute(select(Job).where(Job.id == j_superseded))).scalar_one()
    j_row2.status = "superseded"
    j_row2.finished_at = old_ts
    await db_session.flush()

    # Execute the retention DELETE on the test session
    result = await db_session.execute(
        sa.delete(Job)
        .where(
            sa.or_(
                sa.and_(
                    Job.status == "succeeded",
                    Job.finished_at < (now - timedelta(days=settings.JOB_RETENTION_SUCCEEDED_DAYS)),
                ),
                sa.and_(
                    Job.status.in_(["failed", "cancelled", "superseded"]),
                    Job.finished_at < failed_cutoff,
                ),
            )
        )
        .returning(Job.id)
    )
    deleted_ids = {row[0] for row in result.all()}
    await db_session.flush()

    assert j_cancelled in deleted_ids, "old cancelled job should be deleted"
    assert j_superseded in deleted_ids, "old superseded job should be deleted"

    for gone_id in (j_cancelled, j_superseded):
        r = await db_session.execute(select(Job).where(Job.id == gone_id))
        assert r.scalar_one_or_none() is None, f"job {gone_id} must be gone"
