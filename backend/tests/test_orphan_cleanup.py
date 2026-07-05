"""Tests for the daily orphan_cleanup scheduled task (Fix Set 8).

Covers two reclamation halves:
  - _purge_trash: soft-deleted item folders under DATA_DIR/trash older than
    TRASH_RETENTION_DAYS are hard-deleted; newer ones are kept; disabled at 0.
  - _reclaim_orphaned_prints: files under an item's prints/ dir with no
    referencing PrintRecord are reported (default) or deleted (opt-in), while
    referenced files are always left alone.

The trash tests are pure-filesystem (DATA_DIR is pointed at tmp_path by the
autouse isolated_data_dir fixture). The orphaned-prints tests commit Library /
Item / PrintRecord rows to the ephemeral Postgres (because _reclaim_orphaned_prints
opens its own SessionLocal), then clean them up.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)


def _make_old(path: Path, days: int) -> None:
    """Backdate a path's mtime by *days* days."""
    old = time.time() - days * 86400
    os.utime(path, (old, old))


# ---------------------------------------------------------------------------
# Trash purge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_trash_removes_old_keeps_new(monkeypatch: Any, tmp_path: Path) -> None:
    from app.worker.tasks.scheduled import _purge_trash  # noqa: PLC0415

    monkeypatch.setattr("app.config.settings.TRASH_RETENTION_DAYS", 30)

    trash = tmp_path / "trash"
    trash.mkdir()

    old_entry = trash / "20200101T000000Z-oldkey"
    old_entry.mkdir()
    (old_entry / "model.stl").write_bytes(b"x" * 100)
    _make_old(old_entry, days=40)

    new_entry = trash / "20260101T000000Z-newkey"
    new_entry.mkdir()
    (new_entry / "model.stl").write_bytes(b"y" * 50)
    # new_entry keeps its fresh mtime

    purged, reclaimed = await _purge_trash(datetime.now(UTC))

    assert purged == 1
    assert reclaimed >= 100
    assert not old_entry.exists(), "old trash entry should have been purged"
    assert new_entry.exists(), "new trash entry must be kept"


@pytest.mark.asyncio
async def test_purge_trash_disabled_when_zero(monkeypatch: Any, tmp_path: Path) -> None:
    from app.worker.tasks.scheduled import _purge_trash  # noqa: PLC0415

    monkeypatch.setattr("app.config.settings.TRASH_RETENTION_DAYS", 0)

    trash = tmp_path / "trash"
    trash.mkdir()
    old_entry = trash / "20200101T000000Z-oldkey"
    old_entry.mkdir()
    (old_entry / "f.bin").write_bytes(b"z" * 10)
    _make_old(old_entry, days=999)

    purged, reclaimed = await _purge_trash(datetime.now(UTC))

    assert purged == 0
    assert reclaimed == 0
    assert old_entry.exists(), "purge must be disabled at TRASH_RETENTION_DAYS=0"


@pytest.mark.asyncio
async def test_purge_trash_no_dir_is_noop(monkeypatch: Any, tmp_path: Path) -> None:
    from app.worker.tasks.scheduled import _purge_trash  # noqa: PLC0415

    monkeypatch.setattr("app.config.settings.TRASH_RETENTION_DAYS", 30)
    # No trash dir created under tmp_path.
    purged, reclaimed = await _purge_trash(datetime.now(UTC))
    assert (purged, reclaimed) == (0, 0)


# ---------------------------------------------------------------------------
# Orphaned prints — needs committed DB rows
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def prints_item(tmp_path: Path) -> Any:
    """Commit a Library + Item + one PrintRecord, and lay out a prints/ dir.

    The item's prints/ dir contains one referenced file (linked by the
    PrintRecord) and one orphan file. Yields (item_id, referenced_path,
    orphan_path). Cleans up committed rows afterward.
    """
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415
    from app.models.print_record import PrintRecord  # noqa: PLC0415

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)

    # Patch the module-level SessionLocal so _reclaim_orphaned_prints' internal
    # session uses this NullPool engine bound to the current test loop — avoids the
    # "attached to a different loop" error when co-located with other async tests
    # under xdist (same pattern as render_item_setup in test_render_reliability).
    import app.db as app_db_mod  # noqa: PLC0415

    original_sl = app_db_mod.SessionLocal
    app_db_mod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    item_dir = tmp_path / "orphan-prints-item"
    prints_dir = item_dir / "prints"
    prints_dir.mkdir(parents=True, exist_ok=True)

    referenced = prints_dir / "kept.gcode"
    referenced.write_bytes(b"G1 X0\n" * 10)
    orphan = prints_dir / "orphan.gcode"
    orphan.write_bytes(b"G1 Y0\n" * 20)

    item_id = -1
    lib_id = -1
    async with AsyncSession(engine, expire_on_commit=False) as db:
        lib = Library(name="orphan_cleanup_lib", mount_path=str(tmp_path / "lib"))
        db.add(lib)
        await db.flush()

        item = Item(
            key="orphan1",
            title="Orphan Prints Test Item",
            slug="orphan-prints-item",
            library_id=lib.id,
            dir_path=str(item_dir),
            schema_version=1,
        )
        db.add(item)
        await db.flush()

        rec = PrintRecord(
            item_id=item.id,
            gcode_file_path=str(referenced.relative_to(item_dir)),
        )
        db.add(rec)
        await db.commit()
        item_id = item.id
        lib_id = lib.id

    yield item_id, referenced, orphan

    async with AsyncSession(engine, expire_on_commit=False) as db:
        await db.execute(sa.delete(PrintRecord).where(PrintRecord.item_id == item_id))
        await db.execute(sa.delete(Item).where(Item.id == item_id))
        await db.execute(sa.delete(Library).where(Library.id == lib_id))
        await db.commit()
    app_db_mod.SessionLocal = original_sl
    await engine.dispose()


@pytest.mark.asyncio
async def test_orphaned_prints_report_only_keeps_files(
    prints_item: Any, monkeypatch: Any
) -> None:
    """Default (ORPHAN_PRINTS_DELETE=False): orphan is reported, nothing deleted."""
    from app.worker.tasks.scheduled import _reclaim_orphaned_prints  # noqa: PLC0415

    _item_id, referenced, orphan = prints_item
    monkeypatch.setattr("app.config.settings.ORPHAN_PRINTS_DELETE", False)

    found, total_bytes = await _reclaim_orphaned_prints(datetime.now(UTC))

    assert found == 1, "the one orphan should be reported"
    assert total_bytes > 0
    assert orphan.exists(), "report-only mode must NOT delete the orphan"
    assert referenced.exists(), "referenced file must never be touched"


@pytest.mark.asyncio
async def test_orphaned_prints_delete_removes_old_orphan_keeps_referenced(
    prints_item: Any, monkeypatch: Any
) -> None:
    """ORPHAN_PRINTS_DELETE=True: an OLD orphan is deleted; referenced file kept."""
    from app.worker.tasks.scheduled import _reclaim_orphaned_prints  # noqa: PLC0415

    _item_id, referenced, orphan = prints_item
    monkeypatch.setattr("app.config.settings.ORPHAN_PRINTS_DELETE", True)
    monkeypatch.setattr("app.config.settings.TRASH_RETENTION_DAYS", 30)

    # Age the orphan past the retention window so it qualifies for deletion.
    _make_old(orphan, days=45)

    deleted, deleted_bytes = await _reclaim_orphaned_prints(datetime.now(UTC))

    assert deleted == 1
    assert deleted_bytes > 0
    assert not orphan.exists(), "old orphan should be deleted in delete mode"
    assert referenced.exists(), "referenced file must never be deleted"


@pytest.mark.asyncio
async def test_orphaned_prints_delete_keeps_young_orphan(
    prints_item: Any, monkeypatch: Any
) -> None:
    """ORPHAN_PRINTS_DELETE=True but orphan younger than retention → kept."""
    from app.worker.tasks.scheduled import _reclaim_orphaned_prints  # noqa: PLC0415

    _item_id, referenced, orphan = prints_item
    monkeypatch.setattr("app.config.settings.ORPHAN_PRINTS_DELETE", True)
    monkeypatch.setattr("app.config.settings.TRASH_RETENTION_DAYS", 30)
    # orphan keeps its fresh mtime (younger than 30 days)

    deleted, _ = await _reclaim_orphaned_prints(datetime.now(UTC))

    assert deleted == 0, "a young orphan must not be deleted"
    assert orphan.exists()
    assert referenced.exists()
