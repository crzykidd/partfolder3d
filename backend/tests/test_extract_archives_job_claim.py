"""extract_archives must claim its enqueue-time queued Job row (no orphan).

Also covers the data-migration SQL (0027) that supersedes already-orphaned rows.
"""

from __future__ import annotations

import ast
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.job import Job

TEST_DB_URL = __import__("os").environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> Any:
    """Committed Library + Item (dir on disk); SessionLocal patched to NullPool."""
    import app.db as app_db_mod  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    original = app_db_mod.SessionLocal
    app_db_mod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)  # type: ignore[assignment]

    item_dir = tmp_path / "ea-item"
    item_dir.mkdir()
    async with AsyncSession(engine, expire_on_commit=False) as db:
        lib = Library(name="ea_claim_lib", mount_path=str(tmp_path / "lib"))
        db.add(lib)
        await db.flush()
        item = Item(
            key="eaclaim1",
            title="EA Claim Item",
            slug="ea-claim-item",
            library_id=lib.id,
            dir_path=str(item_dir),
            schema_version=1,
        )
        db.add(item)
        await db.flush()
        await db.commit()
        item_id = item.id

    try:
        yield engine, item_id, item_dir
    finally:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            await db.execute(sa.delete(Job).where(Job.item_id == item_id))
            await db.execute(sa.text("DELETE FROM files WHERE item_id = :i"), {"i": item_id})
            await db.execute(sa.text("DELETE FROM items WHERE id = :i"), {"i": item_id})
            await db.execute(sa.text("DELETE FROM libraries WHERE name = 'ea_claim_lib'"))
            await db.commit()
        app_db_mod.SessionLocal = original  # type: ignore[assignment]
        await engine.dispose()


async def _enqueue_queued_row(engine: Any, item_id: int) -> str:
    """Write the queued row via the real enqueue helper; return its arq job id."""
    from app.services.item_helpers import _write_queued_row_and_enqueue  # noqa: PLC0415

    pool = AsyncMock()
    async with AsyncSession(engine, expire_on_commit=False) as db:
        await _write_queued_row_and_enqueue(
            item_id,
            pool=pool,
            db=db,
            task="extract_archives",
            job_type="extract_archives",
        )
        await db.commit()
    return pool.enqueue_job.call_args.kwargs["_job_id"]


async def _rows(engine: Any, item_id: int) -> list[Job]:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        return list(
            (
                await db.execute(
                    select(Job).where(Job.item_id == item_id, Job.type == "extract_archives")
                )
            ).scalars()
        )


@pytest.mark.asyncio
async def test_extract_with_zip_claims_queued_row(env: Any) -> None:
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.worker.tasks.archive import extract_archives  # noqa: PLC0415

    engine, item_id, item_dir = env
    with zipfile.ZipFile(item_dir / "pack.zip", "w") as zf:
        zf.writestr("model.stl", b"solid x\nendsolid x\n")
    async with AsyncSession(engine, expire_on_commit=False) as db:
        db.add(
            File(
                item_id=item_id,
                path="pack.zip",
                role=FileRole.zip,
                size=(item_dir / "pack.zip").stat().st_size,
                sha256="eaclaimzip",
                mtime=datetime.now(UTC),
            )
        )
        await db.commit()

    arq_id = await _enqueue_queued_row(engine, item_id)
    queued = await _rows(engine, item_id)
    assert len(queued) == 1 and queued[0].status == "queued"

    await extract_archives({"job_id": arq_id, "redis": AsyncMock()}, item_id)

    rows = await _rows(engine, item_id)
    assert len(rows) == 1
    assert rows[0].id == queued[0].id
    assert rows[0].status == "succeeded"


@pytest.mark.asyncio
async def test_extract_without_zips_claims_and_finishes(env: Any) -> None:
    from app.worker.tasks.archive import extract_archives  # noqa: PLC0415

    engine, item_id, _ = env
    arq_id = await _enqueue_queued_row(engine, item_id)
    queued = await _rows(engine, item_id)

    await extract_archives({"job_id": arq_id}, item_id)

    rows = await _rows(engine, item_id)
    assert len(rows) == 1
    assert rows[0].id == queued[0].id
    assert rows[0].status == "succeeded"


@pytest.mark.asyncio
async def test_migration_0027_supersedes_only_provably_orphaned(env: Any) -> None:
    path = (
        Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "0027_supersede_orphaned_extract_archives_jobs.py"
    )
    # Read the SQL constant via AST instead of importing the migration: under
    # pytest (cwd=backend/) ``alembic`` resolves to the local ``backend/alembic/``
    # dir, so the migration's ``from alembic import op`` can't be imported here.
    tree = ast.parse(path.read_text())
    sql = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "SUPERSEDE_ORPHANED_SQL" for t in node.targets)
    )

    engine, item_id, _ = env
    now = datetime.now(UTC)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        orphan = Job(
            type="extract_archives", status="queued", payload={}, item_id=item_id,
            created_at=now - timedelta(minutes=5),
        )
        later = Job(
            type="extract_archives", status="succeeded", payload={}, item_id=item_id,
            created_at=now,
        )
        db.add_all([orphan, later])
        await db.commit()
        orphan_id, later_id = orphan.id, later.id

    async def _statuses() -> dict[Any, str]:
        return {j.id: j.status for j in await _rows(engine, item_id)}

    async with engine.begin() as conn:
        await conn.execute(sa.text(sql))
    st = await _statuses()
    assert st[orphan_id] == "superseded"
    assert st[later_id] == "succeeded"

    # Lone queued row (no later sibling) is untouched; rerun is idempotent.
    async with AsyncSession(engine, expire_on_commit=False) as db:
        await db.execute(sa.delete(Job).where(Job.item_id == item_id))
        lone = Job(type="extract_archives", status="queued", payload={}, item_id=item_id)
        db.add(lone)
        await db.commit()
        lone_id = lone.id
    async with engine.begin() as conn:
        await conn.execute(sa.text(sql))
        await conn.execute(sa.text(sql))
    assert (await _statuses())[lone_id] == "queued"
