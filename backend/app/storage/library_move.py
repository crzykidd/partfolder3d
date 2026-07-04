"""Cross-mount item move — copy → verify (hash) → remove (issue #25, docs/atomic-moves.md).

A **library move** relocates an item's on-disk directory from one library mount to
another.  Unlike a same-volume title rename (``journal.atomic_rename``), the source
and target may live on different filesystems (NFS ↔ local), so ``os.replace()`` would
raise ``EXDEV``.  This module implements a copy-then-verify-then-remove move that
upholds the project's absolute invariant:

    **An interrupted move never loses files.**  The source directory stays fully
    intact until every file at the target has been SHA-256-verified against the
    source, and only then is the source removed.

Flow (journaled for crash recovery):

  1. Preflight — source exists, the *final* destination does NOT exist, the target
     parent is creatable/writable.
  2. Write journal (``state=copying``) → ``/data/journal/library_moves/<key>.json``
     (fsync file + dir).
  3. Remove any stale ``<dst>.partial-<key>`` left by a prior interrupted attempt.
  4. Copy source → ``<dst>.partial-<key>`` (``shutil.copytree``; spans devices).
  5. Verify: the file set under the partial target matches the source exactly and
     every file hashes equal (reuses ``inventory.hash_file_sha256``).  On ANY
     mismatch → abort: remove the partial target, delete the journal, leave the
     **source fully intact**, raise ``LibraryMoveError``.
  6. ``os.replace(partial, dst)`` — atomic on the target volume.  ← the target is now
     the canonical copy.
  7. Remove the source dir (``shutil.rmtree``).  Point of no return for the source; a
     failure here leaves a verified target plus a stale source (a duplicate — never
     data loss).
  8. Delete the journal.

Interrupted-safety by construction:

  - Interrupted at steps 2–5 (before the atomic swap): the *final* destination never
    appears and the source is untouched, so the item still resolves at its original
    path.  Recovery removes the orphan ``.partial`` and the journal.
  - Interrupted at steps 6–7 (after the swap, before/**during** source removal): the
    target is a complete, hash-verified copy; the source may survive as a duplicate
    but no file is ever lost.  Recovery finishes the source removal.

This module is **pure** (no DB): it operates on paths + key so it stays unit-testable
on tmp dirs.  The router updates ``library_id`` + ``dir_path`` + re-inventories in its
own transaction after this returns.  (A crash *between* a successful move and the DB
commit cannot lose files — it can only leave the DB pointing at the vacated path,
which the reconcile engine surfaces as an Issue for the admin, exactly like an
irrecoverable post-commit rename.)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import settings
from .inventory import hash_file_sha256
from .journal import _fsync_dir

log = logging.getLogger(__name__)


class LibraryMoveError(Exception):
    """Raised when a library move fails and the source was left fully intact."""


# ---------------------------------------------------------------------------
# Journal (separate sub-dir so it never collides with the rename journal glob)
# ---------------------------------------------------------------------------


@dataclass
class LibraryMoveJournalEntry:
    key: str
    src_dir: str
    dst_dir: str
    state: str  # "copying"
    timestamp: str  # ISO-8601 UTC


def _library_move_journal_dir() -> Path:
    return Path(settings.DATA_DIR) / "journal" / "library_moves"


def _library_move_journal_path(key: str) -> Path:
    return _library_move_journal_dir() / f"{key}.json"


def _partial_path(dst_dir: Path, key: str) -> Path:
    """Sibling scratch dir for the in-progress copy (same target volume as dst)."""
    return dst_dir.with_name(f"{dst_dir.name}.partial-{key}")


def _write_library_move_journal(entry: LibraryMoveJournalEntry) -> None:
    journal_dir = _library_move_journal_dir()
    journal_dir.mkdir(parents=True, exist_ok=True)
    path = _library_move_journal_path(entry.key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(entry), indent=2), encoding="utf-8")
    with tmp.open("rb") as fh:
        os.fsync(fh.fileno())
    tmp.replace(path)
    _fsync_dir(journal_dir)


def _delete_library_move_journal(key: str) -> None:
    path = _library_move_journal_path(key)
    path.unlink(missing_ok=True)
    jdir = _library_move_journal_dir()
    if jdir.exists():
        _fsync_dir(jdir)


def _read_library_move_journal(key: str) -> LibraryMoveJournalEntry | None:
    path = _library_move_journal_path(key)
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return LibraryMoveJournalEntry(**d)
    except Exception:
        log.exception("Failed to parse library-move journal %s", path)
        return None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _relative_files(root: Path) -> dict[str, Path]:
    """Map every file under *root* to its path relative to *root* (POSIX str)."""
    out: dict[str, Path] = {}
    for entry in root.rglob("*"):
        if entry.is_file() or (entry.is_symlink() and not entry.is_dir()):
            out[entry.relative_to(root).as_posix()] = entry
    return out


def _verify_copy(src_dir: Path, dst_dir: Path) -> None:
    """Assert dst_dir is a byte-for-byte copy of src_dir (set + per-file SHA-256).

    Raises LibraryMoveError on any discrepancy.
    """
    src_files = _relative_files(src_dir)
    dst_files = _relative_files(dst_dir)

    missing = set(src_files) - set(dst_files)
    if missing:
        raise LibraryMoveError(
            f"Copy verification failed: {len(missing)} file(s) missing at target "
            f"(e.g. {sorted(missing)[0]!r})"
        )
    extra = set(dst_files) - set(src_files)
    if extra:
        raise LibraryMoveError(
            f"Copy verification failed: {len(extra)} unexpected file(s) at target "
            f"(e.g. {sorted(extra)[0]!r})"
        )

    for rel, src_path in src_files.items():
        src_hash = hash_file_sha256(src_path)
        dst_hash = hash_file_sha256(dst_files[rel])
        if src_hash != dst_hash:
            raise LibraryMoveError(
                f"Copy verification failed: hash mismatch for {rel!r} "
                f"(source {src_hash[:12]}… vs target {dst_hash[:12]}…)"
            )


# ---------------------------------------------------------------------------
# The move
# ---------------------------------------------------------------------------


def move_item_to_library(src_dir: Path, dst_dir: Path, key: str) -> Path:
    """Relocate an item directory to a new library mount, copy→verify→remove.

    Pure filesystem operation (no DB).  Interrupted-safe: the source is never
    removed until the target is a hash-verified copy.

    Args:
        src_dir: Current absolute item directory (under the source library mount).
        dst_dir: Target absolute item directory (under the target library mount).
                 Computed by the caller via ``paths.item_dir_path``.
        key:     Item key (stable; used for the journal + partial-dir name).

    Returns:
        The target directory path (``dst_dir``) on success.

    Raises:
        LibraryMoveError: on any pre-swap failure — the source is left fully intact
            and no partial target survives.
    """
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)

    # ---- Step 1: Preflight (nothing mutated) ----
    if not src_dir.exists():
        raise LibraryMoveError(f"Source directory does not exist: {src_dir}")
    if not src_dir.is_dir():
        raise LibraryMoveError(f"Source path is not a directory: {src_dir}")
    if dst_dir.resolve() == src_dir.resolve():
        raise LibraryMoveError(f"Source and target are the same directory: {src_dir}")
    if dst_dir.exists():
        raise LibraryMoveError(f"Target directory already exists: {dst_dir}")

    dst_parent = dst_dir.parent
    try:
        dst_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LibraryMoveError(
            f"Cannot create target parent directory {dst_parent}: {exc}"
        ) from exc
    if not os.access(dst_parent, os.W_OK):
        raise LibraryMoveError(f"Target parent directory is not writable: {dst_parent}")

    partial = _partial_path(dst_dir, key)

    # ---- Step 2: Journal ----
    entry = LibraryMoveJournalEntry(
        key=key,
        src_dir=str(src_dir),
        dst_dir=str(dst_dir),
        state="copying",
        timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    _write_library_move_journal(entry)

    try:
        # ---- Step 3: Clear any stale partial from a prior interrupted attempt ----
        if partial.exists():
            shutil.rmtree(partial)

        # ---- Step 4: Copy → partial (spans devices) ----
        shutil.copytree(src_dir, partial, symlinks=True)

        # ---- Step 5: Verify (source still intact) ----
        _verify_copy(src_dir, partial)

        # Durably flush the copied tree before the swap.
        _fsync_dir(partial)
        _fsync_dir(dst_parent)
    except LibraryMoveError:
        # Verification failed — clean the partial, keep the source, drop the journal.
        _safe_rmtree(partial)
        _delete_library_move_journal(key)
        raise
    except OSError as exc:
        _safe_rmtree(partial)
        _delete_library_move_journal(key)
        raise LibraryMoveError(
            f"Failed to copy {src_dir} → {dst_dir} for key {key}: {exc}"
        ) from exc

    # ---- Step 6: Atomic swap partial → final dst (same target volume) ----
    try:
        partial.replace(dst_dir)
    except OSError as exc:
        _safe_rmtree(partial)
        _delete_library_move_journal(key)
        raise LibraryMoveError(
            f"Failed to finalize target {dst_dir} for key {key}: {exc}"
        ) from exc
    _fsync_dir(dst_parent)

    # ---- Step 7: Remove the source (target is now canonical + verified) ----
    src_parent = src_dir.parent
    _safe_rmtree(src_dir)
    if src_parent.exists():
        _fsync_dir(src_parent)

    # ---- Step 8: Done ----
    _delete_library_move_journal(key)
    log.info("Library move complete for key %s: %s → %s", key, src_dir, dst_dir)
    return dst_dir


def _safe_rmtree(path: Path) -> None:
    """rmtree that never raises (best-effort cleanup)."""
    try:
        if path.exists():
            shutil.rmtree(path)
    except OSError:
        log.exception("Failed to remove directory %s (best-effort)", path)


# ---------------------------------------------------------------------------
# Startup recovery (filesystem-only — reconciles to a single canonical copy)
# ---------------------------------------------------------------------------


def recover_stale_library_moves() -> None:
    """Reconcile leftovers from interrupted library moves (filesystem only).

    Called at worker/app startup.  For each stale journal:

      - final dst exists  → the atomic swap committed → remove the (duplicate)
        source if it survived, then drop the journal.
      - final dst missing → the swap never happened → the source is canonical →
        remove the orphan partial copy, then drop the journal.

    Never removes a directory that would leave the item with zero copies.  DB
    reconciliation (library_id / dir_path) is left to the reconcile engine, which
    surfaces a mismatch as an Issue.
    """
    journal_dir = _library_move_journal_dir()
    if not journal_dir.exists():
        return

    for journal_file in sorted(journal_dir.glob("*.json")):
        key = journal_file.stem
        entry = _read_library_move_journal(key)
        if entry is None:
            log.warning("Unreadable library-move journal: %s — skipping", journal_file)
            continue

        src_dir = Path(entry.src_dir)
        dst_dir = Path(entry.dst_dir)
        partial = _partial_path(dst_dir, key)

        if dst_dir.exists():
            # Swap committed. Remove the vacated source duplicate if present.
            log.info(
                "Library-move recovery: swap committed for key %s; "
                "cleaning source %s", key, src_dir,
            )
            _safe_rmtree(partial)
            if src_dir.exists():
                _safe_rmtree(src_dir)
            _delete_library_move_journal(key)
        elif src_dir.exists():
            # Swap never happened; source is canonical. Drop the orphan partial.
            log.info(
                "Library-move recovery: rolling back for key %s; "
                "removing partial %s", key, partial,
            )
            _safe_rmtree(partial)
            _delete_library_move_journal(key)
        else:
            # Neither final target nor source exists — ambiguous, do not guess.
            log.error(
                "Library-move recovery: neither source (%s) nor target (%s) exists "
                "for key %s — leaving journal for admin review",
                src_dir, dst_dir, key,
            )
