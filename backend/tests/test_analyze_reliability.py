"""Analyze-reliability tests (issue #37 fixes #2 and #4).

Mirrors ``test_render_reliability.py``'s pattern: ``run_analyze_subprocess`` is
mocked at the source-module level so these tests exercise ``analyze_item``'s
error handling without spawning real child processes (the subprocess module
itself is covered by ``test_analyze_subprocess.py``).

Covers:
  - analyze_item: AnalyzeTimeout / AnalyzeError from the subprocess → the file
    is marked errored, the Job ends 'failed', and — critically — the task
    returns normally (the worker survives; it does not crash or hang).
  - analyze_item: AnalyzeCapSkip → NOT an error. A low-confidence stub result
    is stored (sha-keyed, so it is cached and never retried) and the Job
    still finishes successfully.
"""

from __future__ import annotations

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

TEST_DB_URL = __import__("os").environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def analyze_item_setup(tmp_path: Path) -> Any:
    """Create a Library + Item + File in the test DB (committed) + patch SessionLocal.

    Creates a minimal STL file on disk so analyze_item's file-existence check
    passes (the actual analysis is mocked in every test below, so the file's
    content never matters). Yields the item_id; cleans up afterwards.
    """
    import app.db as app_db_mod  # noqa: PLC0415
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    null_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    null_session_local = async_sessionmaker(null_engine, expire_on_commit=False)

    original_sl = app_db_mod.SessionLocal
    app_db_mod.SessionLocal = null_session_local  # type: ignore[assignment]

    item_dir = tmp_path / "test-analyze-reliability-rel8888"
    item_dir.mkdir(parents=True, exist_ok=True)

    # Minimal STL (80-byte header + 4-byte tri count = 84 bytes, 0 triangles).
    # Never actually loaded — run_analyze_subprocess is mocked in every test.
    stl_file = item_dir / "model.stl"
    stl_file.write_bytes(b"\x00" * 80 + b"\x00\x00\x00\x00")

    item_id: int = -1
    lib_id: int = -1
    file_sha = "d" * 64

    async with AsyncSession(null_engine, expire_on_commit=False) as setup_db:
        lib = Library(name="analyze_reliability_lib", mount_path=str(tmp_path / "lib"))
        setup_db.add(lib)
        await setup_db.flush()

        item = Item(
            key="rel8888",
            title="Analyze Reliability Test Item",
            slug="test-analyze-item-rel8888",
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
            sha256=file_sha,
            mtime=datetime.now(UTC),
        )
        setup_db.add(file_row)
        await setup_db.commit()

        item_id = item.id
        lib_id = lib.id

    yield item_id

    async with AsyncSession(null_engine, expire_on_commit=False) as cleanup_db:
        await cleanup_db.execute(sa.delete(Job).where(Job.item_id == item_id))
        await cleanup_db.execute(sa.text("DELETE FROM files WHERE item_id = :i"), {"i": item_id})
        await cleanup_db.execute(sa.delete(Item).where(Item.id == item_id))
        await cleanup_db.execute(sa.delete(Library).where(Library.id == lib_id))
        await cleanup_db.commit()

    app_db_mod.SessionLocal = original_sl  # type: ignore[assignment]
    await null_engine.dispose()


async def _get_job_by_item(item_id: int) -> Job | None:
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
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await db.execute(
                sa.select(sa.func.count()).select_from(Job).where(Job.item_id == item_id)
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


async def _get_object_analysis(item_id: int) -> dict[str, Any] | None:
    from app.models.file import File  # noqa: PLC0415

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await db.execute(
                sa.select(File).where(File.item_id == item_id)
            )
            row = result.scalars().first()
            return row.object_analysis if row is not None else None
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Tests: analyze_item with mocked run_analyze_subprocess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_item_timeout_marks_job_failed_worker_survives(
    analyze_item_setup: int,
) -> None:
    """AnalyzeTimeout from the subprocess → job ends 'failed'; task returns normally.

    This is the worker-survives contract at the heart of issue #37 fix #2: a
    poison mesh's subprocess timing out must NOT crash or hang analyze_item —
    it must mark the one file errored and let the Job finalize.
    """
    from app.worker.analyze_subprocess import AnalyzeTimeout  # noqa: PLC0415
    from app.worker.tasks.analysis import analyze_item  # noqa: PLC0415

    item_id = analyze_item_setup

    with patch(
        "app.worker.analyze_subprocess.run_analyze_subprocess",
        new_callable=AsyncMock,
        side_effect=AnalyzeTimeout("analyze timed out after 300s for model.stl"),
    ):
        # Must return normally — no exception propagates, no hang.
        await analyze_item({}, item_id)

    job = await _get_job_by_item(item_id)
    assert job is not None, "Job row was not created"
    assert job.status == "failed", f"Expected 'failed', got {job.status!r}"
    assert job.finished_at is not None, "Job was not finalized (finished_at is None)"

    count = await _count_jobs_for_item(item_id)
    assert count == 1, f"Expected exactly 1 Job row (no duplicates), got {count}"


@pytest.mark.asyncio
async def test_analyze_item_error_marks_job_failed_worker_survives(
    analyze_item_setup: int,
) -> None:
    """AnalyzeError (subprocess crash/OOM) → job ends 'failed'; task returns normally."""
    from app.worker.analyze_subprocess import AnalyzeError  # noqa: PLC0415
    from app.worker.tasks.analysis import analyze_item  # noqa: PLC0415

    item_id = analyze_item_setup

    with patch(
        "app.worker.analyze_subprocess.run_analyze_subprocess",
        new_callable=AsyncMock,
        side_effect=AnalyzeError("out of memory (RLIMIT_AS bound): ..."),
    ):
        await analyze_item({}, item_id)

    job = await _get_job_by_item(item_id)
    assert job is not None, "Job row was not created"
    assert job.status == "failed", f"Expected 'failed', got {job.status!r}"

    count = await _count_jobs_for_item(item_id)
    assert count == 1, f"Expected exactly 1 Job row (no duplicates), got {count}"


@pytest.mark.asyncio
async def test_analyze_item_cap_skip_stores_stub_and_job_succeeds(
    analyze_item_setup: int,
) -> None:
    """AnalyzeCapSkip → NOT an error: low-confidence stub stored, Job succeeds."""
    from app.worker.analyze_subprocess import AnalyzeCapSkip  # noqa: PLC0415
    from app.worker.tasks.analysis import analyze_item  # noqa: PLC0415

    item_id = analyze_item_setup

    with patch(
        "app.worker.analyze_subprocess.run_analyze_subprocess",
        new_callable=AsyncMock,
        side_effect=AnalyzeCapSkip("model.stl has 5,000,000 triangles (cap 2,000,000)"),
    ):
        await analyze_item({}, item_id)

    job = await _get_job_by_item(item_id)
    assert job is not None, "Job row was not created"
    # Cap-skip is not an error — the item's only file is entirely skipped, so
    # analyzed=0 but errors=0 too → succeeded.
    assert job.status == "succeeded", f"Expected 'succeeded', got {job.status!r}"

    stub = await _get_object_analysis(item_id)
    assert stub is not None, "expected a stub object_analysis to be stored"
    assert stub["analysis_skipped"] == "too_large"
    assert stub["low_confidence"] is True
    assert stub["total_objects"] == 0
    assert stub["source_hash"] == "d" * 64
