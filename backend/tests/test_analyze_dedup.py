"""Dedup concurrent/duplicate analyze jobs per item (issue #37 fix #3).

Two independent guards, both scoped to the ``analyze`` job type only (render
and extract are unaffected):

  1. **Claim-time (PRIMARY).** In ``_analyze_item_inner``, right after the Job
     row is claimed, a query checks whether ANOTHER analyze Job for the same
     item is already ``running`` (excluding the current job id). If so, this
     job is marked ``superseded`` and returns BEFORE the expensive
     ``_analyze_item_body`` runs.
  2. **Enqueue-time (opt-in, churn reduction).** ``_write_queued_row_and_enqueue``
     accepts ``dedup_active=True`` (passed only from ``_enqueue_analyze``) — when
     a non-terminal (queued/running) analyze Job already exists for the item,
     the enqueue is skipped entirely: no row written, nothing enqueued.

Ephemeral Postgres (:5433), mirroring test_queued_visibility.py /
test_analyze_reliability.py's fixture patterns. No real mesh loads — items in
the claim-time tests have zero model files, so ``_analyze_item_body`` no-ops
naturally; ``_analyze_item_body`` is additionally patched in the dedup-hit
case to prove the expensive body is never invoked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.job import Job

TEST_DB_URL = __import__("os").environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)


# ---------------------------------------------------------------------------
# Fixture — claim-time tests (patched SessionLocal, own engine/connection)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def dedup_item_setup(tmp_path: Path) -> Any:
    """Commit a Library + Item (no model files) and patch app.db.SessionLocal.

    No File rows are created — ``_analyze_item_body`` finds zero model files
    and finishes immediately ("No model files to analyze."), so these tests
    exercise the claim-time dedup guard without touching mesh analysis at all.
    """
    import app.db as app_db_mod  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    null_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    null_session_local = async_sessionmaker(null_engine, expire_on_commit=False)

    original_sl = app_db_mod.SessionLocal
    app_db_mod.SessionLocal = null_session_local  # type: ignore[assignment]

    item_dir = tmp_path / "dedup-analyze-item"
    item_dir.mkdir(parents=True, exist_ok=True)

    item_id = -1
    lib_id = -1
    async with AsyncSession(null_engine, expire_on_commit=False) as setup_db:
        lib = Library(name="dedup_analyze_lib", mount_path=str(tmp_path / "lib"))
        setup_db.add(lib)
        await setup_db.flush()
        item = Item(
            key="dedupana1",
            title="Dedup Analyze Item",
            slug="dedup-analyze-item",
            library_id=lib.id,
            dir_path=str(item_dir),
            schema_version=1,
        )
        setup_db.add(item)
        await setup_db.flush()
        await setup_db.commit()
        item_id = item.id
        lib_id = lib.id

    try:
        yield item_id
    finally:
        async with AsyncSession(null_engine, expire_on_commit=False) as cleanup_db:
            await cleanup_db.execute(sa.delete(Job).where(Job.item_id == item_id))
            await cleanup_db.execute(sa.delete(Item).where(Item.id == item_id))
            await cleanup_db.execute(sa.delete(Library).where(Library.id == lib_id))
            await cleanup_db.commit()
        app_db_mod.SessionLocal = original_sl  # type: ignore[assignment]
        await null_engine.dispose()


async def _get_jobs_for_item(item_id: int) -> list[Job]:
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await db.execute(
                sa.select(Job).where(Job.item_id == item_id).order_by(Job.created_at)
            )
            return list(result.scalars().all())
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 1. Claim-time guard — PRIMARY dedup: supersede when a peer is already running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_time_supersedes_when_peer_already_running(
    dedup_item_setup: int,
) -> None:
    """A second analyze claim for the same item, while one is 'running', is
    marked 'superseded' and the expensive body never runs."""
    from app.worker.tasks.analysis import analyze_item  # noqa: PLC0415

    item_id = dedup_item_setup

    # Seed an "already running" analyze Job for this item (simulates the peer
    # that is mid-analysis).
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            running_peer = Job(
                type="analyze",
                status="running",
                payload={"item_id": item_id},
                item_id=item_id,
                arq_job_id="dedup-peer-running",
            )
            db.add(running_peer)
            await db.commit()
            peer_id = running_peer.id
    finally:
        await engine.dispose()

    with patch(
        "app.worker.tasks.analysis._analyze_item_body",
        new_callable=AsyncMock,
    ) as mock_body:
        await analyze_item({}, item_id)

    mock_body.assert_not_awaited()

    jobs = await _get_jobs_for_item(item_id)
    assert len(jobs) == 2, f"expected exactly 2 Job rows (peer + new), got {len(jobs)}"

    peer = next(j for j in jobs if j.id == peer_id)
    new_job = next(j for j in jobs if j.id != peer_id)

    assert peer.status == "running", "the pre-existing peer must be untouched"
    assert new_job.status == "superseded", (
        f"the new claim must be superseded, got {new_job.status!r}"
    )
    assert new_job.finished_at is not None
    assert new_job.error and "deduped" in new_job.error.lower()


@pytest.mark.asyncio
async def test_claim_time_no_peer_runs_normally_not_superseded(
    dedup_item_setup: int,
) -> None:
    """With NO other running analyze job, the job runs normally — the guard
    must not false-positive, and a job never supersedes itself."""
    from app.worker.tasks.analysis import analyze_item  # noqa: PLC0415

    item_id = dedup_item_setup

    await analyze_item({}, item_id)

    jobs = await _get_jobs_for_item(item_id)
    assert len(jobs) == 1, f"expected exactly 1 Job row, got {len(jobs)}"
    assert jobs[0].status == "succeeded", (
        f"expected 'succeeded' (no model files, no dedup), got {jobs[0].status!r}"
    )
    assert jobs[0].status != "superseded"


# ---------------------------------------------------------------------------
# 2. Enqueue-time guard — opt-in dedup, analyze only
# ---------------------------------------------------------------------------


async def _make_item(db: AsyncSession, tmp_path: Path, key: str) -> int:
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    lib = Library(name=f"dedup_enq_lib_{key}", mount_path=str(tmp_path / f"lib_{key}"))
    db.add(lib)
    await db.flush()

    item = Item(
        key=key,
        title=f"Dedup Enqueue Item {key}",
        slug=f"dedup-enqueue-item-{key}",
        library_id=lib.id,
        dir_path=str(tmp_path / f"item_{key}"),
        schema_version=1,
    )
    db.add(item)
    await db.flush()
    return item.id


@pytest.mark.asyncio
async def test_enqueue_analyze_skips_when_active_job_exists(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """_enqueue_analyze (dedup_active=True) writes NO row and enqueues nothing
    when a queued/running analyze Job already exists for the item."""
    from app.services.item_helpers import _enqueue_analyze  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="dedupenq1")
    db_session.add(
        Job(
            type="analyze",
            status="running",
            payload={"item_id": item_id},
            item_id=item_id,
            arq_job_id="dedup-existing-active",
        )
    )
    await db_session.flush()

    pool = AsyncMock()
    await _enqueue_analyze(item_id, pool=pool, db=db_session)

    rows = (
        await db_session.execute(sa.select(Job).where(Job.item_id == item_id))
    ).scalars().all()
    assert len(rows) == 1, "no new Job row should have been written"
    pool.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_analyze_enqueues_once_when_no_active_job(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """With no existing active analyze Job, _enqueue_analyze still enqueues
    exactly once (unchanged behavior when there is nothing to dedup against)."""
    from app.services.item_helpers import _enqueue_analyze  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="dedupenq2")
    pool = AsyncMock()

    await _enqueue_analyze(item_id, pool=pool, db=db_session)

    rows = (
        await db_session.execute(sa.select(Job).where(Job.item_id == item_id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "queued"
    pool.enqueue_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_enqueue_render_not_affected_by_dedup(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """_enqueue_render (dedup_active defaults False) still enqueues even when
    an active render Job already exists for the item — render behavior must
    stay unchanged by the analyze-only dedup guard."""
    from app.services.item_helpers import _enqueue_render  # noqa: PLC0415

    item_id = await _make_item(db_session, tmp_path, key="dedupenq3")
    db_session.add(
        Job(
            type="render",
            status="running",
            payload={"item_id": item_id},
            item_id=item_id,
            arq_job_id="dedup-render-active",
        )
    )
    await db_session.flush()

    pool = AsyncMock()
    await _enqueue_render(item_id, pool=pool, db=db_session)

    rows = (
        await db_session.execute(sa.select(Job).where(Job.item_id == item_id))
    ).scalars().all()
    assert len(rows) == 2, "render must still write a second queued row (no dedup)"
    pool.enqueue_job.assert_awaited_once()
