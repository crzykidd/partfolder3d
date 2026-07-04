"""Queued-job visibility tests (issues #20, #30).

Covers the enqueue-time ``queued`` Job row + the worker's claim-or-create seam:

  - The enqueue helpers write a ``queued`` Job row BEFORE any worker runs, keyed
    on a self-assigned arq job id, and enqueue with that id + a defer.
  - ``claim_or_create_job`` transitions the pre-existing ``queued`` row to
    ``running`` (same row id — no duplicate) and inserts a running row only when
    no queued row exists (retries / scheduled / direct enqueues / lost race).
  - ``analyze_item`` now creates AND finishes a Job row (#30).
  - Queued rows surface through the item-jobs and admin jobs endpoints.

Ephemeral Postgres (:5433) + per-test rollback, like the other suites.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.models.job import Job

TEST_DB_URL = __import__("os").environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_item(db: AsyncSession, tmp_path: Path, key: str = "qv0001") -> int:
    """Create a Library + Item in *db* (flushed, not committed). Returns item id."""
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    lib = Library(name=f"qv_lib_{key}", mount_path=str(tmp_path / f"lib_{key}"))
    db.add(lib)
    await db.flush()

    item = Item(
        key=key,
        title=f"Queued Visibility Item {key}",
        slug=f"qv-item-{key}",
        library_id=lib.id,
        dir_path=str(tmp_path / f"item_{key}"),
        schema_version=1,
    )
    db.add(item)
    await db.flush()
    return item.id


# ---------------------------------------------------------------------------
# 1. Enqueue helpers write a queued row before any worker runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_render_writes_queued_row(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """_enqueue_render writes a queued Job row + enqueues with _job_id/_defer_by."""
    from app.services.item_helpers import _enqueue_render  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="qvren1")
    pool = AsyncMock()

    await _enqueue_render(item_id, pool=pool, db=db_session)

    rows = (
        await db_session.execute(select(Job).where(Job.item_id == item_id))
    ).scalars().all()
    assert len(rows) == 1, "exactly one queued Job row must exist after enqueue"
    row = rows[0]
    assert row.status == "queued"
    assert row.type == "render"
    assert row.arq_job_id, "queued row must carry the self-assigned arq job id"
    assert row.started_at is None

    call = pool.enqueue_job.call_args
    assert call.args == ("render_item", item_id)
    # The arq job id is pinned to the queued row so the worker can claim it.
    assert call.kwargs["_job_id"] == row.arq_job_id
    assert "_defer_by" in call.kwargs


@pytest.mark.asyncio
async def test_enqueue_analyze_writes_queued_row(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """_enqueue_analyze writes a queued Job row of type 'analyze' (#30)."""
    from app.services.item_helpers import _enqueue_analyze  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="qvana1")
    pool = AsyncMock()

    await _enqueue_analyze(item_id, pool=pool, db=db_session)

    row = (
        await db_session.execute(select(Job).where(Job.item_id == item_id))
    ).scalar_one()
    assert row.status == "queued"
    assert row.type == "analyze"
    assert pool.enqueue_job.call_args.args == ("analyze_item", item_id)


@pytest.mark.asyncio
async def test_enqueue_without_db_writes_no_row_but_still_enqueues(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """db=None (caller without a session) → no queued row, but still enqueues."""
    from app.services.item_helpers import _enqueue_analyze  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="qvnodb")
    pool = AsyncMock()

    await _enqueue_analyze(item_id, pool=pool, db=None)

    rows = (
        await db_session.execute(select(Job).where(Job.item_id == item_id))
    ).scalars().all()
    assert rows == []
    pool.enqueue_job.assert_awaited_once()
    # No queued row → no id pinned; the worker falls back to claim-or-create.
    assert "_job_id" not in pool.enqueue_job.call_args.kwargs


@pytest.mark.asyncio
async def test_enqueue_render_failure_never_blocks(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """A raising enqueue is swallowed — item work must never be blocked."""
    from app.services.item_helpers import _enqueue_render  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="qvfail")
    pool = AsyncMock()
    pool.enqueue_job.side_effect = RuntimeError("redis down")

    # Must not raise.
    await _enqueue_render(item_id, pool=pool, db=db_session)


# ---------------------------------------------------------------------------
# 2. claim_or_create_job: transition the queued row, no duplicate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_transitions_queued_row_no_duplicate(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """The worker claims the pre-existing queued row (same id) — no duplicate."""
    from app.services.item_helpers import _enqueue_render  # noqa: PLC0415
    from app.worker.job_tracker import claim_or_create_job  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="qvclm1")
    pool = AsyncMock()
    await _enqueue_render(item_id, pool=pool, db=db_session)

    queued = (
        await db_session.execute(select(Job).where(Job.item_id == item_id))
    ).scalar_one()
    assert queued.status == "queued"
    arq_id = queued.arq_job_id

    # Worker starts: claim by the same arq job id.
    claimed_id = await claim_or_create_job(
        db_session,
        "render",
        payload={"item_id": item_id},
        item_id=item_id,
        arq_job_id=arq_id,
    )

    assert claimed_id == queued.id, "claim must reuse the same row id"
    rows = (
        await db_session.execute(select(Job).where(Job.item_id == item_id))
    ).scalars().all()
    assert len(rows) == 1, "no duplicate row for the same arq_job_id"
    assert rows[0].status == "running"
    assert rows[0].started_at is not None


@pytest.mark.asyncio
async def test_claim_or_create_inserts_when_no_queued_row(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """No queued row (retry / scheduled / direct enqueue) → insert a running row."""
    from app.worker.job_tracker import claim_or_create_job  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="qvins1")

    jid = await claim_or_create_job(
        db_session,
        "render",
        payload={"item_id": item_id},
        item_id=item_id,
        arq_job_id="never-enqueued-a-row",
    )

    row = (await db_session.execute(select(Job).where(Job.id == jid))).scalar_one()
    assert row.status == "running"
    assert row.item_id == item_id


@pytest.mark.asyncio
async def test_claim_is_atomic_single_winner(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Race path: a second claim of the same queued row finds nothing to claim.

    Simulates the worker popping the job (claim #1 wins) while a duplicate claim
    attempt (claim #2) sees the row already running — proving at most one running
    row survives per arq_job_id even under a claim race.
    """
    from app.services.item_helpers import _enqueue_render  # noqa: PLC0415
    from app.worker.job_tracker import claim_queued_job  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="qvrace")
    pool = AsyncMock()
    await _enqueue_render(item_id, pool=pool, db=db_session)
    arq_id = (
        await db_session.execute(select(Job).where(Job.item_id == item_id))
    ).scalar_one().arq_job_id

    first = await claim_queued_job(db_session, arq_id)
    second = await claim_queued_job(db_session, arq_id)

    assert first is not None
    assert second is None, "only the first claim wins; the queued row is gone"


# ---------------------------------------------------------------------------
# 3. analyze_item creates AND finishes a Job row (#30)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def analyze_item_setup(tmp_path: Path) -> Any:
    """Commit a Library + Item + STL File and patch SessionLocal (NullPool).

    Yields the item id; cleans up all created rows afterwards.
    """
    import app.db as app_db_mod  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    null_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    null_session_local = async_sessionmaker(null_engine, expire_on_commit=False)

    original_sl = app_db_mod.SessionLocal
    app_db_mod.SessionLocal = null_session_local  # type: ignore[assignment]

    item_dir = tmp_path / "qv-analyze-item"
    item_dir.mkdir(parents=True, exist_ok=True)
    stl_file = item_dir / "model.stl"
    stl_file.write_bytes(b"\x00" * 80 + b"\x00\x00\x00\x00")

    item_id = -1
    async with AsyncSession(null_engine, expire_on_commit=False) as setup_db:
        lib = Library(name="qv_analyze_lib", mount_path=str(tmp_path / "lib"))
        setup_db.add(lib)
        await setup_db.flush()
        item = Item(
            key="qvanalyze",
            title="QV Analyze Item",
            slug="qv-analyze-item",
            library_id=lib.id,
            dir_path=str(item_dir),
            schema_version=1,
        )
        setup_db.add(item)
        await setup_db.flush()
        setup_db.add(
            File(
                item_id=item.id,
                path="model.stl",
                role=FileRole.model,
                size=stl_file.stat().st_size,
                sha256="qvanalyzesha",
                mtime=datetime.now(UTC),
            )
        )
        await setup_db.commit()
        item_id = item.id

    try:
        yield item_id
    finally:
        async with AsyncSession(null_engine, expire_on_commit=False) as cleanup_db:
            await cleanup_db.execute(sa.delete(Job).where(Job.item_id == item_id))
            await cleanup_db.execute(
                sa.text("DELETE FROM files WHERE item_id = :i"), {"i": item_id}
            )
            await cleanup_db.execute(sa.delete(Item).where(Item.id == item_id))
            await cleanup_db.commit()
        app_db_mod.SessionLocal = original_sl  # type: ignore[assignment]
        await null_engine.dispose()


@pytest.mark.asyncio
async def test_analyze_item_creates_and_finishes_job(analyze_item_setup: int) -> None:
    """analyze_item with no pre-existing queued row → creates + finishes a Job."""
    from app.worker.tasks.analysis import analyze_item  # noqa: PLC0415

    item_id = analyze_item_setup

    # Empty ctx → arq_job_id None → claim-or-create inserts a running row.
    await analyze_item({}, item_id)

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            rows = (
                await db.execute(
                    select(Job).where(Job.item_id == item_id, Job.type == "analyze")
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert len(rows) == 1, "analyze_item must create exactly one analyze Job row"
    assert rows[0].status in ("succeeded", "failed")
    assert rows[0].finished_at is not None


@pytest.mark.asyncio
async def test_analyze_item_claims_existing_queued_row(analyze_item_setup: int) -> None:
    """analyze_item claims a pre-written queued row instead of duplicating it."""
    from app.worker.tasks.analysis import analyze_item  # noqa: PLC0415

    item_id = analyze_item_setup
    arq_id = "qv-analyze-arq-id"

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(
                Job(
                    type="analyze",
                    status="queued",
                    payload={"item_id": item_id},
                    item_id=item_id,
                    arq_job_id=arq_id,
                )
            )
            await db.commit()

        await analyze_item({"job_id": arq_id}, item_id)

        async with AsyncSession(engine, expire_on_commit=False) as db:
            rows = (
                await db.execute(
                    select(Job).where(Job.item_id == item_id, Job.type == "analyze")
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert len(rows) == 1, "the queued row must be claimed, not duplicated"
    assert rows[0].arq_job_id == arq_id
    assert rows[0].status in ("succeeded", "failed")
    assert rows[0].finished_at is not None


# ---------------------------------------------------------------------------
# 4. Queued rows surface through the read endpoints
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> str:
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


@pytest.mark.asyncio
async def test_queued_rows_visible_via_endpoints(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    """A queued Job row surfaces in both the item-jobs and admin jobs endpoints."""
    csrf = await _setup_and_login(client)
    item_id = await _make_item(db_session, tmp_path, key="qvend1")

    # Fetch the item key for the item-jobs endpoint.
    from app.models.item import Item  # noqa: PLC0415

    item = (
        await db_session.execute(select(Item).where(Item.id == item_id))
    ).scalar_one()
    item_key = item.key

    db_session.add(
        Job(
            type="render",
            status="queued",
            payload={"item_id": item_id},
            item_id=item_id,
            arq_job_id="qv-endpoint-arq",
        )
    )
    await db_session.commit()

    # Item-jobs endpoint (active = queued/running)
    resp = await client.get(f"/api/items/{item_key}/jobs")
    assert resp.status_code == 200, resp.text
    statuses = [j["status"] for j in resp.json()]
    assert "queued" in statuses

    # Admin jobs endpoint, filtered to queued
    resp = await client.get("/api/jobs?status=queued", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any(j["status"] == "queued" for j in body["jobs"])
