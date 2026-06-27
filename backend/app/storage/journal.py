"""Journaled atomic directory rename — the move engine (docs/atomic-moves.md).

The contract:
  1. Preflight (verify) — nothing mutated yet.
  2. Write journal → /data/journal/<key>.json (fsync).
  3. os.replace(old_dir, new_dir) ← COMMIT POINT.
  4. Finish-forward: rewrite sidecar + update DB.
  5. Delete journal.

Failure semantics:
  - Pre-commit (steps 1–3):  os.replace() is atomic and raises on EXDEV or
    permission issues → nothing has changed → delete journal, release lock,
    report error.
  - Post-commit (steps 4–5): new dir exists → roll-forward idempotently.
    A failed sidecar write self-heals via the scheduled Sync job.

Startup recovery (recover_stale_journals()):
  For each stale journal file in /data/journal/*.json:
    new dir exists, old gone  → finish forward.
    old dir exists, new gone  → roll back.
    both / neither            → log + leave journal (admin attention needed).

Bulk = N independent per-item transactions (no global lock).  One bad item
never blocks or rolls back other items.

Locking strategy: asyncio.Lock() per key, stored in an in-process dict.
This is sufficient for the single-process FastAPI server.  If the worker
or a future multi-process deployment needs cross-process locking, replace
_per_item_locks with Redis/Redlock — the interface stays the same.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-item asyncio locks (keyed by item key string)
# ---------------------------------------------------------------------------

_lock_registry: dict[str, asyncio.Lock] = {}
_lock_registry_lock = asyncio.Lock()


async def _get_item_lock(key: str) -> asyncio.Lock:
    """Return (and lazily create) the per-item asyncio.Lock."""
    async with _lock_registry_lock:
        if key not in _lock_registry:
            _lock_registry[key] = asyncio.Lock()
        return _lock_registry[key]


# ---------------------------------------------------------------------------
# Journal file helpers
# ---------------------------------------------------------------------------

def _journal_dir() -> Path:
    return Path(settings.DATA_DIR) / "journal"


def _journal_path(key: str) -> Path:
    return _journal_dir() / f"{key}.json"


@dataclass
class JournalEntry:
    key: str
    old_dir: str
    new_dir: str
    old_title: str
    new_title: str
    old_slug: str
    new_slug: str
    state: str  # "renaming"
    timestamp: str  # ISO-8601 UTC


def _fsync_dir(directory: Path) -> None:
    """fsync a directory (durably write directory entries to disk).

    Uses os.open(O_RDONLY) because opening a directory via Path.open()
    raises IsADirectoryError on Linux.
    """
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_journal(entry: JournalEntry) -> None:
    """Write and fsync the journal file."""
    journal_dir = _journal_dir()
    journal_dir.mkdir(parents=True, exist_ok=True)
    path = _journal_path(entry.key)
    tmp = path.with_suffix(".tmp")
    data = json.dumps(asdict(entry), indent=2)
    tmp.write_text(data, encoding="utf-8")
    with tmp.open("rb") as fh:
        os.fsync(fh.fileno())
    tmp.replace(path)
    # fsync the journal directory
    _fsync_dir(journal_dir)


def _delete_journal(key: str) -> None:
    """Remove the journal file and fsync the directory."""
    path = _journal_path(key)
    path.unlink(missing_ok=True)
    jdir = _journal_dir()
    if jdir.exists():
        _fsync_dir(jdir)


def _read_journal(key: str) -> JournalEntry | None:
    """Read a journal file, returning None if missing or malformed."""
    path = _journal_path(key)
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return JournalEntry(**d)
    except Exception:
        log.exception("Failed to parse journal file %s", path)
        return None


# ---------------------------------------------------------------------------
# Sidecar + DB finish-forward helpers
# ---------------------------------------------------------------------------

async def _finish_forward_sidecar(
    new_dir: Path,
    new_title: str,
    new_slug: str,
    key: str,
    db: AsyncSession,
) -> None:
    """Rewrite the sidecar in new_dir with the new title/slug.

    Non-fatal: if this fails, the sidecar self-heals on the next Sync job.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from ..models.file import File  # noqa: PLC0415
    from ..models.image import Image  # noqa: PLC0415
    from ..models.item import Item  # noqa: PLC0415
    from ..models.tag import ItemTag, Tag  # noqa: PLC0415
    from .sidecar import SidecarFile, SidecarImage, build_sidecar, write_sidecar  # noqa: PLC0415

    try:
        result = await db.execute(
            select(Item).where(Item.key == key)
        )
        item = result.scalar_one_or_none()
        if item is None:
            log.warning("finish_forward_sidecar: no item found for key %s", key)
            return

        # Build tag list
        tag_result = await db.execute(
            select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
            .where(ItemTag.item_id == item.id)
        )
        tags = [t.name for t in tag_result.scalars().all()]

        # Build file list
        file_result = await db.execute(
            select(File).where(File.item_id == item.id)
        )
        sidecar_files = [
            SidecarFile(
                path=f.path,
                role=f.role.value,
                size=f.size,
                sha256=f.sha256,
                mtime=f.mtime.strftime("%Y-%m-%dT%H:%M:%SZ") if f.mtime else None,
            )
            for f in file_result.scalars().all()
        ]

        # Build image list
        img_result = await db.execute(
            select(Image).where(Image.item_id == item.id).order_by(Image.order)
        )
        images_list = img_result.scalars().all()
        sidecar_images = [
            SidecarImage(path=img.path, source=img.source.value, order=img.order)
            for img in images_list
        ]
        default_img = next(
            (img.path for img in images_list if img.is_default), None
        )

        data = build_sidecar(
            item,
            tags=tags,
            files=sidecar_files,
            images=sidecar_images,
            default_image=default_img,
        )
        write_sidecar(new_dir, data, new_title, key)
    except Exception:
        log.exception("finish_forward_sidecar: failed for key %s (non-fatal)", key)


async def _finish_forward_db(
    key: str,
    new_title: str,
    new_slug: str,
    new_dir: str,
    db: AsyncSession,
) -> None:
    """Update the DB row for the item with the new title/slug/dir_path."""
    from sqlalchemy import update  # noqa: PLC0415

    from ..models.item import Item  # noqa: PLC0415

    await db.execute(
        update(Item)
        .where(Item.key == key)
        .values(
            title=new_title,
            slug=new_slug,
            dir_path=new_dir,
            updated_at=datetime.now(UTC),
        )
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Core atomic rename
# ---------------------------------------------------------------------------

class MoveError(Exception):
    """Raised when a rename fails pre-commit (nothing was changed)."""


async def atomic_rename(
    key: str,
    old_dir: Path,
    new_dir: Path,
    old_title: str,
    new_title: str,
    old_slug: str,
    new_slug: str,
    db: AsyncSession,
) -> None:
    """Perform a journaled atomic directory rename for an item.

    Acquires the per-item lock, writes the journal, renames the directory
    (commit point), then finishes forward.  On pre-commit failure, raises
    MoveError with the user-facing reason.

    Args:
        key:        Item key (stable, never changes).
        old_dir:    Current absolute item directory path.
        new_dir:    Target absolute item directory path.
        old_title:  Current item title.
        new_title:  New item title.
        old_slug:   Current slug.
        new_slug:   New slug.
        db:         Async DB session for post-commit DB update.

    Raises:
        MoveError: if any pre-commit check fails (nothing mutated).
        OSError:   if os.replace() fails for an unexpected reason.
    """
    lock = await _get_item_lock(key)
    async with lock:
        # ---- Step 1: Preflight ----
        if not old_dir.exists():
            raise MoveError(f"Source directory does not exist: {old_dir}")
        if new_dir.exists():
            raise MoveError(f"Target directory already exists: {new_dir}")
        parent = old_dir.parent
        if not os.access(parent, os.W_OK):
            raise MoveError(f"Parent directory is not writable: {parent}")

        # Refuse cross-device renames (would become a copy, not a rename).
        try:
            old_dev = old_dir.stat().st_dev
            parent_dev = parent.stat().st_dev
            if old_dev != parent_dev:
                raise MoveError(
                    f"Cross-device rename refused for key {key}: "
                    f"{old_dir} → {new_dir}"
                )
        except OSError as exc:
            raise MoveError(f"Cannot stat paths for key {key}: {exc}") from exc

        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ---- Step 2: Write journal (fsync) ----
        entry = JournalEntry(
            key=key,
            old_dir=str(old_dir),
            new_dir=str(new_dir),
            old_title=old_title,
            new_title=new_title,
            old_slug=old_slug,
            new_slug=new_slug,
            state="renaming",
            timestamp=now_iso,
        )
        _write_journal(entry)

        # ---- Step 3: COMMIT POINT — atomic rename ----
        try:
            old_dir.replace(new_dir)
        except OSError as exc:
            # Pre-commit failure: nothing changed. Clean up journal.
            _delete_journal(key)
            # EXDEV = cross-device link (mount point crossed unexpectedly)
            if exc.errno == 18:  # EXDEV
                raise MoveError(
                    f"Cross-device rename refused for key {key}: {exc}"
                ) from exc
            raise MoveError(
                f"Directory rename failed for key {key} "
                f"({old_dir} → {new_dir}): {exc}"
            ) from exc

        # ---- Steps 4–5: Finish-forward (post-commit) ----
        await _finish_forward_sidecar(new_dir, new_title, new_slug, key, db)
        await _finish_forward_db(key, new_title, new_slug, str(new_dir), db)
        _delete_journal(key)


# ---------------------------------------------------------------------------
# Startup recovery sweep
# ---------------------------------------------------------------------------

async def recover_stale_journals(db: AsyncSession) -> None:
    """Recover any stale journal files left by interrupted rename operations.

    Called at application startup (and safe to call again during scan/Rescan).

    For each journal file found:
      - new dir exists, old gone → rename committed → finish-forward → delete journal.
      - old dir exists, new gone → rename never happened → roll back (DB/sidecar
        already reflect old name) → delete journal.
      - both exist or neither    → ambiguous → log + leave journal.
    """
    journal_dir = _journal_dir()
    if not journal_dir.exists():
        return

    for journal_file in sorted(journal_dir.glob("*.json")):
        key = journal_file.stem
        entry = _read_journal(key)
        if entry is None:
            log.warning("Unreadable journal file: %s — skipping", journal_file)
            continue

        old_dir = Path(entry.old_dir)
        new_dir = Path(entry.new_dir)
        old_exists = old_dir.exists()
        new_exists = new_dir.exists()

        if new_exists and not old_exists:
            # Rename committed; finish forward.
            log.info(
                "Recovery: finishing forward for key %s (%s → %s)",
                key, old_dir, new_dir,
            )
            await _finish_forward_sidecar(new_dir, entry.new_title, entry.new_slug, key, db)
            await _finish_forward_db(key, entry.new_title, entry.new_slug, str(new_dir), db)
            _delete_journal(key)
            log.info("Recovery: finished for key %s", key)

        elif old_exists and not new_exists:
            # Rename never happened; ensure DB/sidecar reflect old name.
            log.info(
                "Recovery: rolling back for key %s (%s never renamed)",
                key, old_dir,
            )
            # DB and sidecar may or may not have been updated; re-apply old values.
            await _finish_forward_db(key, entry.old_title, entry.old_slug, str(old_dir), db)
            await _finish_forward_sidecar(old_dir, entry.old_title, entry.old_slug, key, db)
            _delete_journal(key)
            log.info("Recovery: rolled back for key %s", key)

        else:
            # Ambiguous (both exist or neither exist) — do not guess.
            log.error(
                "Recovery: ambiguous journal for key %s "
                "(old_exists=%s, new_exists=%s) — leaving journal for admin review: %s",
                key, old_exists, new_exists, journal_file,
            )
            # Phase 6 will surface this as an Issue.  For now, log clearly.


# ---------------------------------------------------------------------------
# Trash helper (used by item delete)
# ---------------------------------------------------------------------------

def move_to_trash(item_dir: Path, key: str) -> Path:
    """Move item_dir to /data/trash/<timestamp>-<key>/ (no journal needed).

    Delete is not an atomic rename in the library-corruption sense — it's a
    separate explicit user action.  We still move to trash rather than rm -rf
    to honour "never lose data" (PRD §1 design principle).

    Returns the trash destination path.

    Raises:
        OSError: if the move fails (e.g. cross-device).
    """
    trash_dir = Path(settings.DATA_DIR) / "trash"
    trash_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = trash_dir / f"{ts}-{key}"
    item_dir.replace(dest)
    return dest
