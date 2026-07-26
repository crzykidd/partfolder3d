"""Tests for the OpenSCAD server-side render feature (issue #46).

Covers, in order:
  - scad_subprocess.py: the isolated-compile wrapper, fully mocked (no real
    openscad binary needed) — timeout, non-zero exit, empty output, success.
  - _enqueue_scad_compile: the SCAD_RENDER_ENABLED gate.
  - compile_scad_item: the full task (mocked compile step) — generated-asset
    linkage, fallback-on-failure ("store source, skip preview"), the
    no-op/skip paths, and the sha-cache re-compile skip.
  - reconcile: proves the derived STL is NOT flagged as drift/a new file, and
    that it's excluded from the sidecar (a regenerable artifact).
  - A real-openscad integration test, skipped when the binary isn't installed
    (it isn't, on a pre-#46 worker image / most dev/CI hosts) — issue #46's
    "Before you start" gotcha.

No DB test here commits to app.db.SessionLocal without patching it to a
NullPool engine bound to the test's event loop — same rationale as
test_render_reliability.py's render_item_setup fixture: compile_scad_item
opens its OWN SessionLocal() connections internally, which only see
COMMITTED rows, and pytest-asyncio hands each test a fresh event loop.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.file import File, FileRole
from app.models.job import Job

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)

_SCAD_SOURCE = "// Test part\n// A trivial cube.\ncube([2, 2, 2]);\n"


# ---------------------------------------------------------------------------
# Pure-unit tests: scad_subprocess.py (no DB, no real binary)
# ---------------------------------------------------------------------------


def test_openscad_available_true_when_on_path(monkeypatch: Any) -> None:
    from app.worker.scad_subprocess import openscad_available

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/openscad")
    assert openscad_available() is True


def test_openscad_available_false_when_missing(monkeypatch: Any) -> None:
    from app.worker.scad_subprocess import openscad_available

    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert openscad_available() is False


@pytest.mark.asyncio
async def test_run_scad_compile_subprocess_raises_when_binary_missing(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from app.worker.scad_subprocess import ScadCompileError, run_scad_compile_subprocess

    monkeypatch.setattr(shutil, "which", lambda name: None)
    scad = tmp_path / "in.scad"
    scad.write_text(_SCAD_SOURCE)

    with pytest.raises(ScadCompileError, match="not found on PATH"):
        await run_scad_compile_subprocess(
            scad, tmp_path / "out.stl", workdir=tmp_path,
            timeout_s=5, mem_limit_mb=512, cpu_limit_s=5,
        )


@pytest.mark.asyncio
async def test_run_scad_compile_subprocess_timeout(tmp_path: Path, monkeypatch: Any) -> None:
    from app.worker import scad_subprocess as mod

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/openscad")

    fake_proc = AsyncMock()
    fake_proc.pid = 424242
    fake_proc.communicate = AsyncMock(side_effect=TimeoutError)
    fake_proc.wait = AsyncMock(return_value=0)

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    # _kill_process_group imports os locally — patch the os module itself.
    monkeypatch.setattr("os.killpg", lambda *a, **k: None)

    scad = tmp_path / "in.scad"
    scad.write_text(_SCAD_SOURCE)

    with pytest.raises(mod.ScadTimeout, match="timed out"):
        await mod.run_scad_compile_subprocess(
            scad, tmp_path / "out.stl", workdir=tmp_path,
            timeout_s=1, mem_limit_mb=512, cpu_limit_s=5,
        )


@pytest.mark.asyncio
async def test_run_scad_compile_subprocess_nonzero_exit(tmp_path: Path, monkeypatch: Any) -> None:
    from app.worker import scad_subprocess as mod

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/openscad")

    fake_proc = AsyncMock()
    fake_proc.pid = 424243
    fake_proc.returncode = 1
    fake_proc.communicate = AsyncMock(return_value=(b"", b"ERROR: Parser error"))

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    scad = tmp_path / "in.scad"
    scad.write_text("this is not valid scad {{{")

    with pytest.raises(mod.ScadCompileError, match="Parser error"):
        await mod.run_scad_compile_subprocess(
            scad, tmp_path / "out.stl", workdir=tmp_path,
            timeout_s=5, mem_limit_mb=512, cpu_limit_s=5,
        )


@pytest.mark.asyncio
async def test_run_scad_compile_subprocess_empty_output(tmp_path: Path, monkeypatch: Any) -> None:
    """returncode 0 but no STL written -> ScadCompileError (not a silent success)."""
    from app.worker import scad_subprocess as mod

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/openscad")

    fake_proc = AsyncMock()
    fake_proc.pid = 424244
    fake_proc.returncode = 0
    fake_proc.communicate = AsyncMock(return_value=(b"", b""))

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    scad = tmp_path / "in.scad"
    scad.write_text(_SCAD_SOURCE)
    out = tmp_path / "out.stl"  # never created

    with pytest.raises(mod.ScadCompileError, match="no/empty output"):
        await mod.run_scad_compile_subprocess(
            scad, out, workdir=tmp_path, timeout_s=5, mem_limit_mb=512, cpu_limit_s=5,
        )


@pytest.mark.asyncio
async def test_run_scad_compile_subprocess_success(tmp_path: Path, monkeypatch: Any) -> None:
    from app.worker import scad_subprocess as mod

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/openscad")

    scad = tmp_path / "in.scad"
    scad.write_text(_SCAD_SOURCE)
    out = tmp_path / "out.stl"

    fake_proc = AsyncMock()
    fake_proc.pid = 424245
    fake_proc.returncode = 0

    async def fake_communicate() -> tuple[bytes, bytes]:
        out.write_bytes(b"fake stl bytes")
        return (b"", b"")

    fake_proc.communicate = fake_communicate

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await mod.run_scad_compile_subprocess(
        scad, out, workdir=tmp_path, timeout_s=5, mem_limit_mb=512, cpu_limit_s=5,
    )
    assert out.read_bytes() == b"fake stl bytes"


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


def test_scad_render_config_defaults() -> None:
    from app.config import settings

    assert settings.SCAD_RENDER_ENABLED is True
    assert settings.SCAD_RENDER_TIMEOUT_S > 0
    assert settings.SCAD_RENDER_MEM_LIMIT_MB >= 512
    assert settings.SCAD_RENDER_CPU_LIMIT_S > 0
    assert settings.SCAD_RENDER_CONCURRENCY >= 1


# ---------------------------------------------------------------------------
# _enqueue_scad_compile gating (uses the transactional db_session fixture)
# ---------------------------------------------------------------------------


async def _make_minimal_item(db: AsyncSession, tmp_path: Path) -> int:
    from app.models.item import Item
    from app.models.library import Library

    lib = Library(name="scad-enqueue-lib", mount_path=str(tmp_path / "lib"))
    db.add(lib)
    await db.flush()

    item_dir = tmp_path / "lib" / "sc" / "scad-item-sc0001"
    item_dir.mkdir(parents=True, exist_ok=True)
    item = Item(
        key="sc0001",
        title="Scad Enqueue Test Item",
        slug="scad-item-sc0001",
        library_id=lib.id,
        dir_path=str(item_dir),
        schema_version=1,
    )
    db.add(item)
    await db.flush()
    return item.id


@pytest.mark.asyncio
async def test_enqueue_scad_compile_disabled_skips(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    from app.config import settings
    from app.services.item_helpers import _enqueue_scad_compile

    item_id = await _make_minimal_item(db_session, tmp_path)
    pool = AsyncMock()

    with patch.object(settings, "SCAD_RENDER_ENABLED", False):
        await _enqueue_scad_compile(item_id, pool=pool, db=db_session)

    pool.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_scad_compile_enabled_enqueues(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    from app.config import settings
    from app.services.item_helpers import _enqueue_scad_compile

    item_id = await _make_minimal_item(db_session, tmp_path)
    pool = AsyncMock()

    with patch.object(settings, "SCAD_RENDER_ENABLED", True):
        await _enqueue_scad_compile(item_id, pool=pool, db=db_session)

    pool.enqueue_job.assert_called_once()
    assert pool.enqueue_job.call_args.args[0] == "compile_scad_item"


# ---------------------------------------------------------------------------
# Task-level integration tests (NullPool-patched SessionLocal, real commits)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def scad_item_setup(tmp_path: Path) -> Any:
    """Create a Library + Item + a .scad source File (committed); patch SessionLocal."""
    import app.db as app_db_mod
    from app.models.item import Item
    from app.models.library import Library

    null_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    null_session_local = async_sessionmaker(null_engine, expire_on_commit=False)

    original_sl = app_db_mod.SessionLocal
    app_db_mod.SessionLocal = null_session_local  # type: ignore[assignment]

    item_dir = tmp_path / "test-scad-item-scd9999"
    item_dir.mkdir(parents=True, exist_ok=True)

    scad_file = item_dir / "part.scad"
    scad_file.write_text(_SCAD_SOURCE)
    scad_sha = hashlib.sha256(scad_file.read_bytes()).hexdigest()

    item_id: int = -1
    lib_id: int = -1
    source_file_id: int = -1

    async with AsyncSession(null_engine, expire_on_commit=False) as setup_db:
        lib = Library(name="scad_task_lib", mount_path=str(tmp_path / "lib"))
        setup_db.add(lib)
        await setup_db.flush()

        item = Item(
            key="scd9999",
            title="Scad Task Test Item",
            slug="test-scad-item-scd9999",
            library_id=lib.id,
            dir_path=str(item_dir),
            schema_version=1,
        )
        setup_db.add(item)
        await setup_db.flush()

        source_file = File(
            item_id=item.id,
            path="part.scad",
            role=FileRole.source,
            size=scad_file.stat().st_size,
            sha256=scad_sha,
            mtime=datetime.now(UTC),
            last_seen_size=scad_file.stat().st_size,
            last_seen_mtime=datetime.now(UTC),
        )
        setup_db.add(source_file)
        await setup_db.commit()

        item_id = item.id
        lib_id = lib.id
        source_file_id = source_file.id

    yield {"item_id": item_id, "item_dir": item_dir, "source_file_id": source_file_id}

    async with AsyncSession(null_engine, expire_on_commit=False) as cleanup_db:
        await cleanup_db.execute(sa.delete(Job).where(Job.item_id == item_id))
        await cleanup_db.execute(sa.delete(File).where(File.item_id == item_id))
        await cleanup_db.execute(
            sa.text("DELETE FROM items WHERE id = :id"), {"id": item_id}
        )
        await cleanup_db.execute(sa.delete(Library).where(Library.id == lib_id))
        await cleanup_db.commit()

    app_db_mod.SessionLocal = original_sl  # type: ignore[assignment]
    await null_engine.dispose()


async def _get_files_for_item(item_id: int) -> list[File]:
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await db.execute(sa.select(File).where(File.item_id == item_id))
            return list(result.scalars().all())
    finally:
        await engine.dispose()


async def _get_job_for_item(item_id: int, job_type: str) -> Job | None:
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await db.execute(
                sa.select(Job).where(Job.item_id == item_id, Job.type == job_type)
            )
            return result.scalars().first()
    finally:
        await engine.dispose()


def _fake_success_compile(content: bytes = b"fake derived stl bytes"):  # type: ignore[no-untyped-def]
    async def _fake(target: Path, out_stl: Path, **kwargs: Any) -> None:
        out_stl.write_bytes(content)

    return _fake


@pytest.mark.asyncio
async def test_compile_scad_item_success_creates_generated_file(
    scad_item_setup: dict[str, Any],
) -> None:
    from app.worker.tasks.scad_render import compile_scad_item

    item_id = scad_item_setup["item_id"]
    source_file_id = scad_item_setup["source_file_id"]

    with (
        patch("app.worker.scad_subprocess.openscad_available", return_value=True),
        patch(
            "app.worker.scad_subprocess.run_scad_compile_subprocess",
            side_effect=_fake_success_compile(),
        ),
    ):
        await compile_scad_item({"redis": AsyncMock()}, item_id)

    files = await _get_files_for_item(item_id)
    generated = [f for f in files if f.generated_from_file_id is not None]
    assert len(generated) == 1
    gen = generated[0]
    assert gen.generated_from_file_id == source_file_id
    assert gen.role == FileRole.model
    assert gen.generated_source_sha256 is not None
    assert gen.path.startswith("generated/")

    job = await _get_job_for_item(item_id, "scad_render")
    assert job is not None
    assert job.status == "succeeded"


@pytest.mark.asyncio
async def test_compile_scad_item_fallback_on_compile_failure(
    scad_item_setup: dict[str, Any],
) -> None:
    """A compile failure (bad geometry / missing include) is a soft skip, not a crash."""
    from app.worker.scad_subprocess import ScadCompileError
    from app.worker.tasks.scad_render import compile_scad_item

    item_id = scad_item_setup["item_id"]

    with (
        patch("app.worker.scad_subprocess.openscad_available", return_value=True),
        patch(
            "app.worker.scad_subprocess.run_scad_compile_subprocess",
            side_effect=ScadCompileError("ERROR: use of undeclared module"),
        ),
    ):
        await compile_scad_item({}, item_id)

    files = await _get_files_for_item(item_id)
    generated = [f for f in files if f.generated_from_file_id is not None]
    assert generated == [], "a failed compile must not leave a partial generated File row"

    job = await _get_job_for_item(item_id, "scad_render")
    assert job is not None
    assert job.status == "succeeded", (
        "an expected compile failure (bad include, missing lib) must not fail the job"
    )
    assert "Skipped" in (job.log or "")


@pytest.mark.asyncio
async def test_compile_scad_item_no_binary_soft_skips(
    scad_item_setup: dict[str, Any],
) -> None:
    from app.worker.tasks.scad_render import compile_scad_item

    item_id = scad_item_setup["item_id"]

    with patch("app.worker.scad_subprocess.openscad_available", return_value=False):
        await compile_scad_item({}, item_id)

    files = await _get_files_for_item(item_id)
    assert all(f.generated_from_file_id is None for f in files)

    job = await _get_job_for_item(item_id, "scad_render")
    assert job is not None
    assert job.status == "succeeded"
    assert "not available" in (job.log or "")


@pytest.mark.asyncio
async def test_compile_scad_item_no_scad_files_is_a_noop(tmp_path: Path) -> None:
    """An item with no .scad source files at all finishes succeeded, no-op."""
    import app.db as app_db_mod
    from app.models.item import Item
    from app.models.library import Library
    from app.worker.tasks.scad_render import compile_scad_item

    null_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    null_session_local = async_sessionmaker(null_engine, expire_on_commit=False)
    original_sl = app_db_mod.SessionLocal
    app_db_mod.SessionLocal = null_session_local  # type: ignore[assignment]

    item_dir = tmp_path / "test-scad-noop-scd0001"
    item_dir.mkdir(parents=True, exist_ok=True)
    item_id = -1
    lib_id = -1
    try:
        async with AsyncSession(null_engine, expire_on_commit=False) as db:
            lib = Library(name="scad_noop_lib", mount_path=str(tmp_path / "lib"))
            db.add(lib)
            await db.flush()
            item = Item(
                key="scd0001",
                title="No Scad Item",
                slug="test-scad-noop-scd0001",
                library_id=lib.id,
                dir_path=str(item_dir),
                schema_version=1,
            )
            db.add(item)
            await db.commit()
            item_id = item.id
            lib_id = lib.id

        await compile_scad_item({}, item_id)

        job = await _get_job_for_item(item_id, "scad_render")
        assert job is not None
        assert job.status == "succeeded"
        assert "No .scad source files" in (job.log or "")
    finally:
        async with AsyncSession(null_engine, expire_on_commit=False) as db:
            await db.execute(sa.delete(Job).where(Job.item_id == item_id))
            await db.execute(sa.text("DELETE FROM items WHERE id = :id"), {"id": item_id})
            await db.execute(sa.delete(Library).where(Library.id == lib_id))
            await db.commit()
        app_db_mod.SessionLocal = original_sl  # type: ignore[assignment]
        await null_engine.dispose()


@pytest.mark.asyncio
async def test_compile_scad_item_skips_recompile_when_source_unchanged(
    scad_item_setup: dict[str, Any],
) -> None:
    """A prior successful compile with a matching generated_source_sha256 is not redone."""
    from app.worker.tasks.scad_render import compile_scad_item

    item_id = scad_item_setup["item_id"]
    source_file_id = scad_item_setup["source_file_id"]

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        src_result = await db.execute(sa.select(File).where(File.id == source_file_id))
        src = src_result.scalar_one()
        db.add(
            File(
                item_id=item_id,
                path="generated/part.stl",
                role=FileRole.model,
                size=10,
                sha256="deadbeef" * 8,
                mtime=datetime.now(UTC),
                last_seen_size=10,
                last_seen_mtime=datetime.now(UTC),
                generated_from_file_id=source_file_id,
                generated_source_sha256=src.sha256,
            )
        )
        await db.commit()
    await engine.dispose()

    with (
        patch("app.worker.scad_subprocess.openscad_available", return_value=True),
        patch(
            "app.worker.scad_subprocess.run_scad_compile_subprocess",
            side_effect=_fake_success_compile(),
        ) as mock_compile,
    ):
        await compile_scad_item({}, item_id)

    mock_compile.assert_not_called()
    job = await _get_job_for_item(item_id, "scad_render")
    assert job is not None
    assert job.status == "succeeded"
    assert "up to date" in (job.log or "")


# ---------------------------------------------------------------------------
# Reconcile: the derived STL must NOT be flagged as drift / a new file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_does_not_flag_generated_stl_as_drift(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    from app.models.item import Item
    from app.models.library import Library
    from app.storage.inventory import hash_file_sha256
    from app.worker.reconcile import reconcile_one_item

    lib = Library(name="scad-reconcile-lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    item_dir = tmp_path / "lib" / "sc" / "scad-reconcile-item"
    item_dir.mkdir(parents=True, exist_ok=True)

    scad_path = item_dir / "part.scad"
    scad_path.write_text(_SCAD_SOURCE)
    stl_dir = item_dir / "generated"
    stl_dir.mkdir()
    stl_path = stl_dir / "part.stl"
    stl_path.write_bytes(b"fake generated stl bytes")

    item = Item(
        key="screc01",
        title="Scad Reconcile Item",
        slug="scad-reconcile-item",
        library_id=lib.id,
        dir_path=str(item_dir),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    scad_stat = scad_path.stat()
    scad_sha = hash_file_sha256(scad_path)
    scad_file = File(
        item_id=item.id,
        path="part.scad",
        role=FileRole.source,
        size=scad_stat.st_size,
        sha256=scad_sha,
        mtime=datetime.fromtimestamp(scad_stat.st_mtime, tz=UTC),
        last_seen_size=scad_stat.st_size,
        last_seen_mtime=datetime.fromtimestamp(scad_stat.st_mtime, tz=UTC),
    )
    db_session.add(scad_file)
    await db_session.flush()

    stl_stat = stl_path.stat()
    stl_sha = hash_file_sha256(stl_path)
    gen_file = File(
        item_id=item.id,
        path="generated/part.stl",
        role=FileRole.model,
        size=stl_stat.st_size,
        sha256=stl_sha,
        mtime=datetime.fromtimestamp(stl_stat.st_mtime, tz=UTC),
        last_seen_size=stl_stat.st_size,
        last_seen_mtime=datetime.fromtimestamp(stl_stat.st_mtime, tz=UTC),
        generated_from_file_id=scad_file.id,
        generated_source_sha256=scad_sha,
    )
    db_session.add(gen_file)
    await db_session.flush()

    result = await reconcile_one_item(db_session, item, source="test")

    assert result.issues_created == [], (
        f"generated STL must not raise Issues (drift/corruption): {result.errors}"
    )
    assert result.review_items_created == [], (
        "generated STL must not be flagged as an unexpected new file"
    )
    assert result.errors == []


@pytest.mark.asyncio
async def test_generated_file_excluded_from_sidecar(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    from app.models.item import Item
    from app.models.library import Library
    from app.services.item_helpers import _build_sidecar_data

    lib = Library(name="scad-sidecar-lib", mount_path=str(tmp_path / "lib"))
    db_session.add(lib)
    await db_session.flush()

    item_dir = tmp_path / "lib" / "sc" / "scad-sidecar-item"
    item_dir.mkdir(parents=True, exist_ok=True)
    item = Item(
        key="scsc01",
        title="Scad Sidecar Item",
        slug="scad-sidecar-item",
        library_id=lib.id,
        dir_path=str(item_dir),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    scad_file = File(
        item_id=item.id,
        path="part.scad",
        role=FileRole.source,
        size=100,
        sha256="a" * 64,
        mtime=datetime.now(UTC),
        last_seen_size=100,
        last_seen_mtime=datetime.now(UTC),
    )
    db_session.add(scad_file)
    await db_session.flush()

    db_session.add(
        File(
            item_id=item.id,
            path="generated/part.stl",
            role=FileRole.model,
            size=200,
            sha256="b" * 64,
            mtime=datetime.now(UTC),
            last_seen_size=200,
            last_seen_mtime=datetime.now(UTC),
            generated_from_file_id=scad_file.id,
            generated_source_sha256="a" * 64,
        )
    )
    await db_session.flush()

    _tags, sidecar_files, _images, _default = await _build_sidecar_data(db_session, item)
    paths = {f.path for f in sidecar_files}

    assert "part.scad" in paths
    assert "generated/part.stl" not in paths


# ---------------------------------------------------------------------------
# Real-binary integration test (skipped when openscad isn't installed)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("openscad") is None,
    reason="openscad binary not installed on this host/CI runner",
)
@pytest.mark.asyncio
async def test_run_scad_compile_subprocess_real_openscad(tmp_path: Path) -> None:
    from app.worker.scad_subprocess import run_scad_compile_subprocess

    scad = tmp_path / "cube.scad"
    scad.write_text("cube([2, 2, 2]);\n")
    out = tmp_path / "cube.stl"

    await run_scad_compile_subprocess(
        scad, out, workdir=tmp_path, timeout_s=30, mem_limit_mb=1024, cpu_limit_s=30,
    )

    assert out.exists()
    assert out.stat().st_size > 0
