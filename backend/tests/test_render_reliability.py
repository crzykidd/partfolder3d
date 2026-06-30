"""Render-reliability tests (subprocess timeout, crash recovery, CancelledError).

These tests exercise the hardened render pipeline introduced alongside
render_subprocess.py:
  - render_item: RenderTimeout → job ends 'failed', not stuck 'running'.
  - render_item: RenderError  → job ends 'failed', no duplicate Job rows.
  - _recover_orphaned_render_jobs: orphaned 'running' render jobs are marked
    'failed' and re-enqueued (dedup by item_id).

No real GL or mesh files are required: run_render_subprocess is mocked at the
source module level so tests can inject RenderTimeout / RenderError without
spawning child processes.

The render_item tests commit data to the ephemeral Postgres (because render_item
opens its own SessionLocal() connections internally, which see only committed
rows).  The render_item_setup fixture also patches app.db.SessionLocal to use a
NullPool engine bound to the current asyncio event loop, avoiding the
"Future attached to a different loop" error that arises when pytest-asyncio
creates a new loop per test but the module-level SessionLocal engine's pool
has connections from the previous loop.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.job import Job

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def render_item_setup(tmp_path: Path) -> Any:
    """Create a Library + Item + File in the test DB (committed) + patch SessionLocal.

    Creates a minimal STL file on disk so render_item's sha256 / file-existence
    checks pass.  Also patches ``app.db.SessionLocal`` to use a fresh NullPool
    engine for this test, so render_item's internal sessions don't share a
    connection-pool that is bound to a previous asyncio event loop.
    Yields the item_id.  Cleans up all created rows after the test.
    """
    import app.db as app_db_mod  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.image import Image  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    # NullPool engine — each acquire creates a fresh connection bound to
    # the current event loop; safe across pytest-asyncio's per-function loops.
    null_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    null_session_local = async_sessionmaker(null_engine, expire_on_commit=False)

    # Patch the module-level SessionLocal so render_item's internal sessions
    # use the NullPool engine.
    original_sl = app_db_mod.SessionLocal
    app_db_mod.SessionLocal = null_session_local  # type: ignore[assignment]

    item_dir = tmp_path / "test-render-item-rel9999"
    item_dir.mkdir(parents=True, exist_ok=True)

    # Minimal STL (80-byte header + 4-byte tri count = 84 bytes, 0 triangles)
    stl_file = item_dir / "model.stl"
    stl_file.write_bytes(b"\x00" * 80 + b"\x00\x00\x00\x00")

    item_id: int = -1
    lib_id: int = -1

    async with AsyncSession(null_engine, expire_on_commit=False) as setup_db:
        lib = Library(name="render_reliability_lib", mount_path=str(tmp_path / "lib"))
        setup_db.add(lib)
        await setup_db.flush()

        item = Item(
            key="rel9999",
            title="Render Reliability Test Item",
            slug="test-render-item-rel9999",
            library_id=lib.id,
            dir_path=str(item_dir),
            schema_version=1,
        )
        setup_db.add(item)
        await setup_db.flush()

        file_row = File(
            item_id=item.id,
            path="model.stl",
            role=FileRole.model,
            size=stl_file.stat().st_size,
            sha256=None,
            mtime=datetime.now(UTC),
        )
        setup_db.add(file_row)
        await setup_db.commit()

        item_id = item.id
        lib_id = lib.id

    yield item_id

    # --- cleanup committed rows ---
    async with AsyncSession(null_engine, expire_on_commit=False) as cleanup_db:
        await cleanup_db.execute(sa.delete(Job).where(Job.item_id == item_id))
        await cleanup_db.execute(sa.delete(Image).where(Image.item_id == item_id))
        await cleanup_db.execute(sa.delete(File).where(File.item_id == item_id))
        await cleanup_db.execute(sa.delete(Item).where(Item.id == item_id))
        await cleanup_db.execute(sa.delete(Library).where(Library.id == lib_id))
        await cleanup_db.commit()

    # Restore original SessionLocal and dispose engine.
    app_db_mod.SessionLocal = original_sl  # type: ignore[assignment]
    await null_engine.dispose()


# ---------------------------------------------------------------------------
# Helper: read a Job row using the same NullPool pattern
# ---------------------------------------------------------------------------


async def _get_job_by_item(item_id: int) -> Job | None:
    """Fetch the first Job row for a given item_id (fresh NullPool session)."""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await db.execute(
                sa.select(Job).where(Job.item_id == item_id).order_by(Job.created_at)
            )
            return result.scalars().first()
    finally:
        await engine.dispose()


async def _count_jobs_for_item(item_id: int) -> int:
    """Count Job rows for a given item_id."""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await db.execute(
                sa.select(sa.func.count()).select_from(Job).where(Job.item_id == item_id)
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Tests: render_item with mocked run_render_subprocess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_item_timeout_marks_job_failed(
    render_item_setup: int,
) -> None:
    """render_item: RenderTimeout from subprocess → job ends 'failed', not 'running'.

    Simulates the per-file timeout path (RenderTimeout raised by the mocked
    run_render_subprocess).  Asserts the Job row is finalized as 'failed' so
    the job is not stuck in 'running' state forever.
    """
    from app.worker.render_subprocess import RenderTimeout  # noqa: PLC0415
    from app.worker.tasks.render import render_item  # noqa: PLC0415

    item_id = render_item_setup

    with patch(
        "app.worker.render_subprocess.run_render_subprocess",
        new_callable=AsyncMock,
        side_effect=RenderTimeout("render timed out after 300s for model.stl"),
    ):
        await render_item({}, item_id)

    job = await _get_job_by_item(item_id)
    assert job is not None, "Job row was not created"
    assert job.status == "failed", f"Expected 'failed', got {job.status!r}"
    assert job.finished_at is not None, "Job was not finalized (finished_at is None)"


@pytest.mark.asyncio
async def test_render_item_render_error_marks_job_failed_no_duplicates(
    render_item_setup: int,
) -> None:
    """render_item: RenderError → job ends 'failed'; only ONE Job row created.

    Asserts that render_item returns normally on RenderError (does not re-raise),
    which prevents arq from auto-retrying and creating duplicate Job rows.
    """
    from app.worker.render_mesh import RenderError  # noqa: PLC0415
    from app.worker.tasks.render import render_item  # noqa: PLC0415

    item_id = render_item_setup

    with patch(
        "app.worker.render_subprocess.run_render_subprocess",
        new_callable=AsyncMock,
        side_effect=RenderError("no rendering backend available"),
    ):
        await render_item({}, item_id)

    job = await _get_job_by_item(item_id)
    assert job is not None, "Job row was not created"
    assert job.status == "failed", f"Expected 'failed', got {job.status!r}"

    count = await _count_jobs_for_item(item_id)
    assert count == 1, f"Expected exactly 1 Job row (no duplicates), got {count}"


# ---------------------------------------------------------------------------
# Tests: _recover_orphaned_render_jobs (uses db_session — function accepts _db)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_orphaned_render_jobs_marks_failed_and_reenqueues(
    db_session: AsyncSession,
) -> None:
    """Orphaned 'running' render job is marked 'failed' and re-enqueued."""
    from worker import _recover_orphaned_render_jobs  # noqa: PLC0415

    item_id = 777001

    # Seed an orphaned render job
    orphan = Job(
        type="render",
        status="running",
        progress=30,
        payload={"item_id": item_id},
        item_id=None,
        started_at=datetime.now(UTC),
    )
    db_session.add(orphan)
    await db_session.flush()

    orphan_id: uuid.UUID = orphan.id

    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    await _recover_orphaned_render_jobs(ctx, _db=db_session)

    # Re-check the row
    result = await db_session.execute(sa.select(Job).where(Job.id == orphan_id))
    updated = result.scalar_one()
    assert updated.status == "failed", f"Expected 'failed', got {updated.status!r}"
    assert "re-queued" in (updated.error or "")

    mock_redis.enqueue_job.assert_called_once_with("render_item", item_id)


@pytest.mark.asyncio
async def test_recover_orphaned_render_jobs_dedup_by_item_id(
    db_session: AsyncSession,
) -> None:
    """Multiple orphaned jobs for the same item_id → only one enqueue."""
    from worker import _recover_orphaned_render_jobs  # noqa: PLC0415

    item_id = 777002

    # Seed two orphaned render jobs for the same item
    for _ in range(2):
        job = Job(
            type="render",
            status="running",
            progress=0,
            payload={"item_id": item_id},
            item_id=None,
            started_at=datetime.now(UTC),
        )
        db_session.add(job)

    # Seed one orphan for a different item
    other_job = Job(
        type="render",
        status="running",
        progress=0,
        payload={"item_id": 777003},
        item_id=None,
        started_at=datetime.now(UTC),
    )
    db_session.add(other_job)
    await db_session.flush()

    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    await _recover_orphaned_render_jobs(ctx, _db=db_session)

    # Both item_ids enqueued; item_id 777002 deduped to one call
    calls = {call.args for call in mock_redis.enqueue_job.call_args_list}
    assert ("render_item", item_id) in calls
    assert ("render_item", 777003) in calls
    assert mock_redis.enqueue_job.call_count == 2, (
        f"Expected 2 enqueue calls (deduped), got {mock_redis.enqueue_job.call_count}"
    )

    # All three orphans should be marked failed
    result = await db_session.execute(
        sa.select(Job).where(
            Job.type == "render",
            Job.status == "running",
        )
    )
    remaining = result.scalars().all()
    assert len(remaining) == 0, "Some orphaned jobs were not marked failed"


@pytest.mark.asyncio
async def test_recover_orphaned_render_jobs_noop_when_clean(
    db_session: AsyncSession,
) -> None:
    """No orphaned jobs → recovery is a no-op; redis is not called."""
    from worker import _recover_orphaned_render_jobs  # noqa: PLC0415

    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    await _recover_orphaned_render_jobs(ctx, _db=db_session)

    mock_redis.enqueue_job.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: RENDER_MODE background-render gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_mode_off_skips_render(render_item_setup: int) -> None:
    """RENDER_MODE=off → render_item returns immediately; no Job row is created."""
    from app.config import settings  # noqa: PLC0415
    from app.worker.tasks.render import render_item  # noqa: PLC0415

    item_id = render_item_setup

    with patch.object(settings, "RENDER_MODE", "off"):
        await render_item({}, item_id)

    assert await _count_jobs_for_item(item_id) == 0, (
        "no Job row should be created when RENDER_MODE=off"
    )


@pytest.mark.asyncio
async def test_render_mode_no_images_skips_when_item_has_images(
    render_item_setup: int,
) -> None:
    """RENDER_MODE=no_images → skip (no Job row) when the item already has an image."""
    from app.config import settings  # noqa: PLC0415
    from app.models.image import Image, ImageSource  # noqa: PLC0415
    from app.worker.tasks.render import render_item  # noqa: PLC0415

    item_id = render_item_setup

    # Give the item an image so the no_images gate skips it.
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(
                Image(
                    item_id=item_id,
                    path="images/existing.png",
                    source=ImageSource.uploaded,
                    is_default=True,
                    order=0,
                )
            )
            await db.commit()
    finally:
        await engine.dispose()

    with patch.object(settings, "RENDER_MODE", "no_images"):
        await render_item({}, item_id)

    assert await _count_jobs_for_item(item_id) == 0, (
        "no Job row should be created when item has images and RENDER_MODE=no_images"
    )
