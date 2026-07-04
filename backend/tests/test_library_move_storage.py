"""Storage-level tests for the cross-mount library move (issue #25).

Pure filesystem tests (tmp dirs, no DB).  Assert the absolute invariant:
**an interrupted move never loses files** — the source stays intact until the
target is hash-verified, then is removed.

Covers:
- happy path: all files relocated, source removed, hashes preserved
- hash-mismatch mid-copy → abort with SOURCE INTACT and no partial target
- copy failure (unreadable/erroring copytree) → abort, source intact
- same-path / missing-source / pre-existing-target rejected
- recovery: committed swap cleans the vacated source; rolled-back move drops the partial
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.storage.inventory import hash_file_sha256
from app.storage.library_move import (
    LibraryMoveError,
    _library_move_journal_path,
    _partial_path,
    move_item_to_library,
    recover_stale_library_moves,
)


def _make_item_dir(root: Path, name: str = "widget-abc123") -> Path:
    """Create a realistic item dir with nested files; return its path."""
    d = root / "ab" / name
    (d / "renders").mkdir(parents=True)
    (d / "images").mkdir(parents=True)
    (d / f"{name}.stl").write_bytes(b"solid model data" * 100)
    (d / "renders" / "thumb.png").write_bytes(b"\x89PNG render bytes" * 50)
    (d / "images" / "photo.jpg").write_bytes(b"jpeg photo bytes" * 30)
    (d / f"{name}.yml").write_text("key: abc123\ntitle: Widget\n")
    return d


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hash_file_sha256(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_move_relocates_all_files_and_removes_source(tmp_path: Path) -> None:
    src_mount = tmp_path / "libA"
    dst_mount = tmp_path / "libB"
    src_dir = _make_item_dir(src_mount)
    before = _hash_tree(src_dir)

    dst_dir = dst_mount / "ab" / "widget-abc123"
    result = move_item_to_library(src_dir, dst_dir, "abc123")

    assert result == dst_dir
    assert dst_dir.is_dir()
    assert not src_dir.exists()  # source removed
    assert _hash_tree(dst_dir) == before  # byte-for-byte
    # No partial + no journal left behind.
    assert not _partial_path(dst_dir, "abc123").exists()
    assert not _library_move_journal_path("abc123").exists()


def test_hash_mismatch_aborts_source_intact(tmp_path: Path) -> None:
    """A verification failure must leave the source fully intact + no partial target."""
    src_dir = _make_item_dir(tmp_path / "libA")
    before = _hash_tree(src_dir)
    dst_dir = tmp_path / "libB" / "ab" / "widget-abc123"

    # Force verification to fail on every file.
    with patch(
        "app.storage.library_move.hash_file_sha256",
        side_effect=lambda p, *a, **k: "deadbeef" if "partial" in str(p) else "cafef00d",
    ):
        with pytest.raises(LibraryMoveError, match="verification failed"):
            move_item_to_library(src_dir, dst_dir, "abc123")

    # SOURCE INTACT — never lose files.
    assert src_dir.is_dir()
    assert _hash_tree(src_dir) == before
    # No partial, no final target, no journal.
    assert not dst_dir.exists()
    assert not _partial_path(dst_dir, "abc123").exists()
    assert not _library_move_journal_path("abc123").exists()


def test_copy_failure_aborts_source_intact(tmp_path: Path) -> None:
    """A mid-copy OSError aborts, keeping the source intact and cleaning the partial."""
    src_dir = _make_item_dir(tmp_path / "libA")
    before = _hash_tree(src_dir)
    dst_dir = tmp_path / "libB" / "ab" / "widget-abc123"

    with patch(
        "app.storage.library_move.shutil.copytree",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(LibraryMoveError, match="Failed to copy"):
            move_item_to_library(src_dir, dst_dir, "abc123")

    assert src_dir.is_dir()
    assert _hash_tree(src_dir) == before
    assert not dst_dir.exists()
    assert not _partial_path(dst_dir, "abc123").exists()
    assert not _library_move_journal_path("abc123").exists()


def test_missing_source_rejected(tmp_path: Path) -> None:
    with pytest.raises(LibraryMoveError, match="does not exist"):
        move_item_to_library(
            tmp_path / "nope", tmp_path / "libB" / "ab" / "x-k", "k"
        )


def test_existing_target_rejected(tmp_path: Path) -> None:
    src_dir = _make_item_dir(tmp_path / "libA")
    dst_dir = tmp_path / "libB" / "ab" / "widget-abc123"
    dst_dir.mkdir(parents=True)
    with pytest.raises(LibraryMoveError, match="already exists"):
        move_item_to_library(src_dir, dst_dir, "abc123")
    # Source untouched.
    assert src_dir.is_dir()


def test_same_path_rejected(tmp_path: Path) -> None:
    src_dir = _make_item_dir(tmp_path / "libA")
    with pytest.raises(LibraryMoveError, match="same directory"):
        move_item_to_library(src_dir, src_dir, "abc123")
    assert src_dir.is_dir()


def test_stale_partial_from_prior_attempt_is_replaced(tmp_path: Path) -> None:
    """A leftover .partial from an interrupted run must not block a fresh move."""
    src_dir = _make_item_dir(tmp_path / "libA")
    before = _hash_tree(src_dir)
    dst_dir = tmp_path / "libB" / "ab" / "widget-abc123"
    partial = _partial_path(dst_dir, "abc123")
    partial.mkdir(parents=True)
    (partial / "garbage.txt").write_text("stale partial from a crash")

    move_item_to_library(src_dir, dst_dir, "abc123")

    assert _hash_tree(dst_dir) == before
    assert not partial.exists()


def test_recover_rolls_forward_when_swap_committed(tmp_path: Path, monkeypatch) -> None:
    """Recovery: target exists (swap done) → remove the vacated source duplicate."""
    monkeypatch.setattr("app.config.settings.DATA_DIR", str(tmp_path / "data"))
    from app.storage import library_move as lm

    src_dir = _make_item_dir(tmp_path / "libA")
    dst_dir = _make_item_dir(tmp_path / "libB")  # simulate: both exist post-swap
    entry = lm.LibraryMoveJournalEntry(
        key="abc123",
        src_dir=str(src_dir),
        dst_dir=str(dst_dir),
        state="copying",
        timestamp="2026-07-04T00:00:00Z",
    )
    lm._write_library_move_journal(entry)

    recover_stale_library_moves()

    assert dst_dir.is_dir()          # canonical target kept
    assert not src_dir.exists()      # vacated source removed
    assert not lm._library_move_journal_path("abc123").exists()


def test_recover_rolls_back_when_swap_never_happened(tmp_path: Path, monkeypatch) -> None:
    """Recovery: target missing (crash before swap) → source canonical, drop partial."""
    monkeypatch.setattr("app.config.settings.DATA_DIR", str(tmp_path / "data"))
    from app.storage import library_move as lm

    src_dir = _make_item_dir(tmp_path / "libA")
    before = _hash_tree(src_dir)
    dst_dir = tmp_path / "libB" / "ab" / "widget-abc123"
    partial = _partial_path(dst_dir, "abc123")
    partial.mkdir(parents=True)
    (partial / "half.txt").write_text("half-copied")
    entry = lm.LibraryMoveJournalEntry(
        key="abc123",
        src_dir=str(src_dir),
        dst_dir=str(dst_dir),
        state="copying",
        timestamp="2026-07-04T00:00:00Z",
    )
    lm._write_library_move_journal(entry)

    recover_stale_library_moves()

    assert _hash_tree(src_dir) == before  # source intact
    assert not partial.exists()           # partial removed
    assert not dst_dir.exists()
    assert not lm._library_move_journal_path("abc123").exists()
