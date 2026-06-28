"""Reconciliation engine — Phase 6 core (PRD §8).

reconcile_one_item() reconciles a single item by running the four §8.1 behaviors.
Called by both the scheduled library scan and the per-item rescan endpoint so both
produce the same Issues / ChangeLog / ReviewItem outcomes.

Behavior modes (per-behavior setting):
  scan.sidecar_sync.mode  = "auto" | "review"   (default: "review")
  scan.re_render.mode     = "auto" | "review"   (default: "auto")
  scan.file_changes.mode  = "auto" | "review"   (default: "review")

Sync-direction rule (sidecar ⇄ DB):
  sidecar_written_at  = parse(sidecar.updated_at)   # timestamp app last wrote sidecar
  sidecar_file_mtime  = OS mtime of sidecar file
  db_updated_at       = item.updated_at

  sidecar_externally_edited = (sidecar_file_mtime − sidecar_written_at) > TOLERANCE
  db_changed_since_sync     = (db_updated_at − sidecar_written_at) > TOLERANCE

  Both changed  → conflict Issue (never auto-clobber)
  Only sidecar  → pull to DB (or ReviewItem if mode=review)
  Only DB       → push to sidecar (always auto — sidecar is a mirror)
  Neither       → skip

URL validation (behavior d) is OFF by default.  Pass a url_validator callable to
enable it.  This ensures unit tests never hit real network.

§8.5 contract: structural fixes go through the journal; the library scan is N
isolated per-item transactions — one bad/locked item fails alone as an Issue and
never blocks or corrupts the rest.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

SIDECAR_SYNC_TOLERANCE_SECONDS = 5.0

# Default per-behavior mode settings (conservative).
DEFAULT_MODES: dict[str, str] = {
    "sidecar_sync": "review",   # structural / potentially destructive
    "re_render": "auto",         # non-destructive
    "file_changes": "review",   # structural
}

# Setting keys used in the settings table.
_SETTING_KEYS = {
    "sidecar_sync": "scan.sidecar_sync.mode",
    "re_render": "scan.re_render.mode",
    "file_changes": "scan.file_changes.mode",
}


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ReconcileResult:
    changes_applied: list[dict] = field(default_factory=list)
    review_items_created: list[int] = field(default_factory=list)
    issues_created: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Settings loader
# ---------------------------------------------------------------------------

async def load_mode_settings(db: AsyncSession) -> dict[str, str]:
    """Read per-behavior scan modes from the settings table.

    Returns a dict with keys "sidecar_sync", "re_render", "file_changes".
    Missing settings fall back to DEFAULT_MODES.
    """
    from ..models.setting import Setting  # noqa: PLC0415

    keys = list(_SETTING_KEYS.values())
    result = await db.execute(select(Setting).where(Setting.key.in_(keys)))
    rows = {r.key: r.value for r in result.scalars().all()}

    modes: dict[str, str] = {}
    for behavior, setting_key in _SETTING_KEYS.items():
        if setting_key in rows:
            try:
                val = json.loads(rows[setting_key])
                if val in ("auto", "review"):
                    modes[behavior] = val
                    continue
            except Exception:
                pass
        modes[behavior] = DEFAULT_MODES[behavior]
    return modes


# ---------------------------------------------------------------------------
# Sidecar write helper (mirrors _write_item_sidecar in items.py without importing it)
# ---------------------------------------------------------------------------

async def _write_sidecar_for_item(db: AsyncSession, item: Any) -> None:
    """Build and write the sidecar for an item from the current DB state."""
    from ..models.file import File  # noqa: I001,PLC0415
    from ..models.image import Image  # noqa: PLC0415
    from ..models.tag import ItemTag, Tag  # noqa: PLC0415
    from ..storage.sidecar import (  # noqa: PLC0415
        SidecarFile,
        SidecarImage,
        build_sidecar,
        write_sidecar,
    )

    tag_result = await db.execute(
        select(Tag).join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item.id)
    )
    tags = [t.name for t in tag_result.scalars().all()]

    file_result = await db.execute(select(File).where(File.item_id == item.id))
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

    img_result = await db.execute(
        select(Image).where(Image.item_id == item.id).order_by(Image.order)
    )
    images_list = img_result.scalars().all()
    sidecar_images = [
        SidecarImage(path=img.path, source=img.source.value, order=img.order)
        for img in images_list
    ]
    default_img = next((img.path for img in images_list if img.is_default), None)

    data = build_sidecar(item, tags=tags, files=sidecar_files, images=sidecar_images,
                         default_image=default_img)
    write_sidecar(Path(item.dir_path), data, item.title, item.key)


# ---------------------------------------------------------------------------
# Behavior (a): Sidecar ⇄ DB bidirectional sync
# ---------------------------------------------------------------------------

async def _behavior_sidecar_sync(
    db: AsyncSession,
    item: Any,
    item_dir: Path,
    sc_name: str,
    modes: dict[str, str],
    result: ReconcileResult,
    source: str,
) -> None:
    from ..models.change_log import ChangeLog  # noqa: PLC0415
    from ..models.issue import Issue, IssueSeverity, IssueStatus, IssueType  # noqa: PLC0415
    from ..models.review_item import ReviewItem  # noqa: PLC0415
    from ..storage.paths import sidecar_path  # noqa: PLC0415
    from ..storage.sidecar import read_sidecar  # noqa: PLC0415

    sc = read_sidecar(item_dir, item.title, item.key)

    if sc is None:
        if not item_dir.exists():
            # Item dir is missing — orphan (no DB row with live dir)
            issue = Issue(
                issue_type=IssueType.orphan,
                severity=IssueSeverity.warning,
                status=IssueStatus.open,
                item_id=item.id,
                detail=f"Item directory missing: {item_dir}",
                suggested_action="Verify the library mount is accessible or delete the item.",
            )
            db.add(issue)
            await db.flush()
            result.issues_created.append(issue.id)
        # No sidecar but dir exists: nothing to sync yet; the next write will create it.
        return

    # Get sidecar file mtime
    sc_path = sidecar_path(item_dir, item.title, item.key)
    try:
        stat = sc_path.stat()
    except OSError:
        return  # sidecar disappeared between read and stat; skip
    sidecar_file_mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

    # Parse the timestamp the app last wrote into the sidecar
    try:
        sidecar_written_at = datetime.fromisoformat(
            sc.updated_at.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        # Can't parse → treat sidecar as externally edited to be safe
        sidecar_written_at = datetime.min.replace(tzinfo=UTC)

    # Ensure item.updated_at is UTC-aware
    db_updated_at = item.updated_at
    if db_updated_at.tzinfo is None:
        db_updated_at = db_updated_at.replace(tzinfo=UTC)

    sidecar_externally_edited = (
        (sidecar_file_mtime - sidecar_written_at).total_seconds()
        > SIDECAR_SYNC_TOLERANCE_SECONDS
    )
    db_changed_since_sync = (
        (db_updated_at - sidecar_written_at).total_seconds()
        > SIDECAR_SYNC_TOLERANCE_SECONDS
    )

    if not sidecar_externally_edited and not db_changed_since_sync:
        return  # In sync

    if sidecar_externally_edited and db_changed_since_sync:
        # Both changed — conflict
        issue = Issue(
            issue_type=IssueType.conflict,
            severity=IssueSeverity.warning,
            status=IssueStatus.open,
            item_id=item.id,
            detail=(
                f"Sidecar and DB both changed since last sync "
                f"(sidecar mtime: {sidecar_file_mtime.isoformat()}, "
                f"DB updated_at: {db_updated_at.isoformat()})"
            ),
            suggested_action=(
                "Review the sidecar file and DB metadata; resolve via the item page."
            ),
        )
        db.add(issue)
        await db.flush()
        result.issues_created.append(issue.id)
        return

    if db_changed_since_sync and not sidecar_externally_edited:
        # DB is newer → push DB state to sidecar (always auto)
        await _write_sidecar_for_item(db, item)
        cl = ChangeLog(
            behavior="sidecar_sync",
            change_type="db_pushed_to_sidecar",
            item_id=item.id,
            summary=f"DB state pushed to sidecar for item {item.key!r} (DB was newer).",
            source=source,
        )
        db.add(cl)
        await db.flush()
        result.changes_applied.append(
            {"behavior": "sidecar_sync", "change_type": "db_pushed_to_sidecar"}
        )
        return

    # Sidecar is newer → pull sidecar fields into DB (or queue for review)
    proposed: dict[str, Any] = {
        "behavior": "sidecar_sync",
        "action": "pull_sidecar_to_db",
        "item_id": item.id,
        "fields": {
            "title": sc.title or item.title,
            "description": sc.description,
            "source_url": sc.source_url,
            "source_site": sc.source_site,
            "license": sc.license,
            "tags": list(sc.tags),
        },
    }

    if modes.get("sidecar_sync") == "auto":
        # Apply immediately
        changed = False
        if sc.title and sc.title != item.title:
            # Title change requires journal rename — just record as issue for safety
            issue = Issue(
                issue_type=IssueType.conflict,
                severity=IssueSeverity.info,
                status=IssueStatus.open,
                item_id=item.id,
                detail=(
                    f"Sidecar title {sc.title!r} differs from DB title {item.title!r}. "
                    "Title renames require user action (atomic rename)."
                ),
                suggested_action="Rename the item via the UI to apply the sidecar title.",
            )
            db.add(issue)
            await db.flush()
            result.issues_created.append(issue.id)
        if sc.description != item.description:
            item.description = sc.description
            changed = True
        if sc.source_url != item.source_url:
            item.source_url = sc.source_url
            changed = True
        if sc.source_site != item.source_site:
            item.source_site = sc.source_site
            changed = True
        if sc.license != item.license:
            item.license = sc.license
            changed = True
        if changed:
            item.updated_at = datetime.now(UTC)
            await db.flush()
        cl = ChangeLog(
            behavior="sidecar_sync",
            change_type="sidecar_pulled_to_db",
            item_id=item.id,
            summary=f"Sidecar fields pulled into DB for item {item.key!r} (sidecar was newer).",
            before_state={"description": item.description, "source_url": item.source_url},
            after_state=proposed["fields"],
            source=source,
        )
        db.add(cl)
        await db.flush()
        result.changes_applied.append(
            {"behavior": "sidecar_sync", "change_type": "sidecar_pulled_to_db"}
        )
    else:
        # Review mode → queue ReviewItem
        rv = ReviewItem(
            behavior="sidecar_sync",
            change_type="sidecar_pulled_to_db",
            item_id=item.id,
            summary=f"Sidecar edited on disk for item {item.key!r}; pull changes into DB?",
            proposed_action=proposed,
        )
        db.add(rv)
        await db.flush()
        result.review_items_created.append(rv.id)


# ---------------------------------------------------------------------------
# Behavior (c): New / removed / extra files
# ---------------------------------------------------------------------------

async def _behavior_file_changes(
    db: AsyncSession,
    item: Any,
    item_dir: Path,
    sc_name: str,
    db_files: list[Any],
    modes: dict[str, str],
    result: ReconcileResult,
    source: str,
) -> None:
    from ..models.change_log import ChangeLog  # noqa: PLC0415
    from ..models.file import File  # noqa: PLC0415
    from ..models.issue import Issue, IssueSeverity, IssueStatus, IssueType  # noqa: PLC0415
    from ..models.review_item import ReviewItem  # noqa: PLC0415
    from ..storage.inventory import inventory_item  # noqa: PLC0415

    if not item_dir.exists():
        # Orphan already recorded by sidecar_sync; skip
        return

    existing = {
        f.path: (f.last_seen_size, f.last_seen_mtime or f.mtime, f.sha256)
        for f in db_files
    }
    records = inventory_item(item_dir, sc_name, existing=existing)

    disk_paths = {r.relative_path for r in records}
    db_paths = {f.path for f in db_files}

    new_paths = disk_paths - db_paths
    missing_paths = db_paths - disk_paths

    # New files on disk not in DB
    for rec in records:
        if rec.relative_path not in new_paths:
            continue
        proposed: dict[str, Any] = {
            "behavior": "file_changes",
            "action": "add_file_row",
            "item_id": item.id,
            "file_path": rec.relative_path,
            "role": rec.role.value,
        }
        if modes.get("file_changes") == "auto":
            f = File(
                item_id=item.id,
                path=rec.relative_path,
                role=rec.role,
                size=rec.size,
                sha256=rec.sha256,
                mtime=rec.mtime,
                last_seen_size=rec.size,
                last_seen_mtime=rec.mtime,
            )
            db.add(f)
            await db.flush()
            cl = ChangeLog(
                behavior="file_changes",
                change_type="file_added",
                item_id=item.id,
                summary=f"New file detected and registered: {rec.relative_path!r}",
                after_state={"path": rec.relative_path, "role": rec.role.value},
                source=source,
            )
            db.add(cl)
            await db.flush()
            result.changes_applied.append({
                "behavior": "file_changes",
                "change_type": "file_added",
                "path": rec.relative_path,
            })
        else:
            rv = ReviewItem(
                behavior="file_changes",
                change_type="file_added",
                item_id=item.id,
                summary=f"New file on disk not yet in DB: {rec.relative_path!r}. Add it?",
                proposed_action=proposed,
            )
            db.add(rv)
            await db.flush()
            result.review_items_created.append(rv.id)

    # Missing files (in DB but not on disk) — always an Issue (never auto-delete)
    for path in missing_paths:
        issue = Issue(
            issue_type=IssueType.missing_file,
            severity=IssueSeverity.warning,
            status=IssueStatus.open,
            item_id=item.id,
            detail=f"File in DB not found on disk: {path!r}",
            suggested_action="Restore the file from backup or remove the record via the item page.",
        )
        db.add(issue)
        await db.flush()
        result.issues_created.append(issue.id)


# ---------------------------------------------------------------------------
# Behavior (b): Re-render on file change
# ---------------------------------------------------------------------------

async def _behavior_re_render(
    db: AsyncSession,
    item: Any,
    item_dir: Path,
    sc_name: str,
    db_files: list[Any],
    modes: dict[str, str],
    result: ReconcileResult,
    source: str,
) -> None:
    from ..models.change_log import ChangeLog  # noqa: I001,PLC0415
    from ..models.file import FileRole  # noqa: PLC0415
    from ..models.review_item import ReviewItem  # noqa: PLC0415
    from ..storage.inventory import _mtime_utc, hash_file_sha256  # noqa: PLC0415
    from ..worker.render_mesh import MESH_EXTENSIONS  # noqa: PLC0415

    if not item_dir.exists():
        return

    model_files = [
        f for f in db_files
        if f.role == FileRole.model
        and Path(f.path).suffix.lower() in MESH_EXTENSIONS
    ]
    if not model_files:
        return

    needs_render = False
    changed_files: list[str] = []

    for f in model_files:
        abs_path = item_dir / f.path
        if not abs_path.exists():
            continue
        try:
            stat = abs_path.stat()
            current_size = stat.st_size
            current_mtime = _mtime_utc(stat)

            # Cheap-first drift check
            prev_size = f.last_seen_size
            prev_mtime = f.last_seen_mtime or f.mtime
            if (
                current_size == prev_size
                and abs((current_mtime - prev_mtime).total_seconds()) < 1.0
                and f.sha256 is not None
            ):
                # No change
                continue

            current_hash = hash_file_sha256(abs_path)
            if current_hash != f.sha256:
                needs_render = True
                changed_files.append(f.path)
        except OSError:
            continue

    if not needs_render:
        return

    proposed: dict[str, Any] = {
        "behavior": "re_render",
        "action": "enqueue_render",
        "item_id": item.id,
        "changed_files": changed_files,
    }

    if modes.get("re_render") == "auto":
        # Enqueue render (fire-and-forget)
        try:
            from arq import create_pool  # noqa: I001,PLC0415
            from arq.connections import RedisSettings  # noqa: PLC0415
            from ..config import settings  # noqa: PLC0415

            redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            await redis.enqueue_job("render_item", item.id)
            await redis.aclose()
        except Exception:
            log.exception("reconcile re_render: failed to enqueue render for item %s", item.id)

        cl = ChangeLog(
            behavior="re_render",
            change_type="render_enqueued",
            item_id=item.id,
            summary=(
                f"Model file(s) changed; re-render enqueued for item"
                f" {item.key!r}: {changed_files}"
            ),
            after_state={"changed_files": changed_files},
            source=source,
        )
        db.add(cl)
        await db.flush()
        result.changes_applied.append({"behavior": "re_render", "change_type": "render_enqueued"})
    else:
        rv = ReviewItem(
            behavior="re_render",
            change_type="render_enqueued",
            item_id=item.id,
            summary=f"Model file(s) changed for item {item.key!r}; re-render?",
            proposed_action=proposed,
        )
        db.add(rv)
        await db.flush()
        result.review_items_created.append(rv.id)


# ---------------------------------------------------------------------------
# Behavior (d): Integrity check — corruption + dead links
# ---------------------------------------------------------------------------

async def _behavior_integrity(
    db: AsyncSession,
    item: Any,
    item_dir: Path,
    sc_name: str,
    db_files: list[Any],
    url_validator: Callable[[str], Awaitable[bool]] | None,
    result: ReconcileResult,
) -> None:
    from ..models.issue import Issue, IssueSeverity, IssueStatus, IssueType  # noqa: PLC0415
    from ..storage.inventory import hash_file_sha256  # noqa: PLC0415

    if not item_dir.exists():
        return

    # Check for file hash corruption
    for f in db_files:
        if f.sha256 is None:
            continue
        abs_path = item_dir / f.path
        if not abs_path.exists():
            continue  # missing_file is handled by file_changes behavior
        try:
            current_hash = hash_file_sha256(abs_path)
            if current_hash != f.sha256:
                issue = Issue(
                    issue_type=IssueType.corruption,
                    severity=IssueSeverity.critical,
                    status=IssueStatus.open,
                    item_id=item.id,
                    detail=(
                        f"File hash mismatch for {f.path!r}: "
                        f"stored={f.sha256[:12]}…, actual={current_hash[:12]}…"
                    ),
                    suggested_action="Verify file integrity; restore from backup if corrupted.",
                )
                db.add(issue)
                await db.flush()
                result.issues_created.append(issue.id)
        except OSError:
            continue

    # Dead-link check — only if a validator was provided (OFF by default)
    if url_validator is not None and item.source_url:
        try:
            reachable = await url_validator(item.source_url)
            if not reachable:
                issue = Issue(
                    issue_type=IssueType.dead_link,
                    severity=IssueSeverity.info,
                    status=IssueStatus.open,
                    item_id=item.id,
                    detail=f"Source URL appears unreachable: {item.source_url}",
                    suggested_action="Verify the URL manually or update/clear the source link.",
                )
                db.add(issue)
                await db.flush()
                result.issues_created.append(issue.id)
        except Exception as exc:
            log.warning("reconcile integrity: url_validator raised for item %s: %s", item.id, exc)


# ---------------------------------------------------------------------------
# Public: reconcile a single item
# ---------------------------------------------------------------------------

async def reconcile_one_item(
    db: AsyncSession,
    item: Any,
    mode_settings: dict[str, str] | None = None,
    url_validator: Callable[[str], Awaitable[bool]] | None = None,
    force_rehash: bool = False,
    source: str = "auto",
) -> ReconcileResult:
    """Reconcile one item: run all 4 §8.1 behaviors.

    Each behavior runs in isolation — a failure is recorded as an Issue and the
    engine continues.  Never crashes the caller; never leaves partial state.

    Args:
        db:            Active async DB session (caller commits).
        item:          Item ORM object (must have id, key, title, dir_path, etc.).
        mode_settings: Per-behavior mode overrides {"sidecar_sync": "auto"|"review", …}.
                       Falls back to DEFAULT_MODES for missing keys.
        url_validator: Async callable (url) → bool. If None, URL validation is skipped.
        force_rehash:  Re-hash all files regardless of drift check (not yet wired).
        source:        ChangeLog source tag ("auto" | "per_item_rescan" | "review_approved").

    Returns:
        ReconcileResult with changes applied, review items created, issues found.
    """
    from ..models.file import File  # noqa: PLC0415
    from ..models.issue import Issue, IssueSeverity, IssueStatus, IssueType  # noqa: PLC0415
    from ..storage.paths import sidecar_name  # noqa: PLC0415

    modes = {**DEFAULT_MODES, **(mode_settings or {})}
    result = ReconcileResult()

    item_dir = Path(item.dir_path)
    sc_name = sidecar_name(item.title, item.key)

    # Load existing File rows
    file_result = await db.execute(select(File).where(File.item_id == item.id))
    db_files = list(file_result.scalars().all())

    # ---- Behavior (a): Sidecar ⇄ DB sync ----
    try:
        await _behavior_sidecar_sync(db, item, item_dir, sc_name, modes, result, source)
    except Exception as exc:
        log.exception("reconcile_one_item: sidecar_sync failed for item %s", item.id)
        result.errors.append(f"sidecar_sync: {exc}")
        _issue = Issue(
            issue_type=IssueType.sidecar_error,
            severity=IssueSeverity.warning,
            status=IssueStatus.open,
            item_id=item.id,
            detail=f"Sidecar sync error: {exc}",
            suggested_action="Re-run rescan or manually inspect the sidecar file.",
        )
        db.add(_issue)
        await db.flush()
        result.issues_created.append(_issue.id)

    # ---- Behavior (c): File changes ----
    try:
        await _behavior_file_changes(db, item, item_dir, sc_name, db_files, modes, result, source)
    except Exception as exc:
        log.exception("reconcile_one_item: file_changes failed for item %s", item.id)
        result.errors.append(f"file_changes: {exc}")
        _issue = Issue(
            issue_type=IssueType.other,
            severity=IssueSeverity.warning,
            status=IssueStatus.open,
            item_id=item.id,
            detail=f"File inventory check failed: {exc}",
        )
        db.add(_issue)
        await db.flush()
        result.issues_created.append(_issue.id)

    # ---- Behavior (b): Re-render on file change ----
    try:
        await _behavior_re_render(db, item, item_dir, sc_name, db_files, modes, result, source)
    except Exception as exc:
        log.exception("reconcile_one_item: re_render check failed for item %s", item.id)
        result.errors.append(f"re_render: {exc}")

    # ---- Behavior (d): Integrity ----
    try:
        await _behavior_integrity(db, item, item_dir, sc_name, db_files, url_validator, result)
    except Exception as exc:
        log.exception("reconcile_one_item: integrity check failed for item %s", item.id)
        result.errors.append(f"integrity: {exc}")

    return result


# ---------------------------------------------------------------------------
# Library-wide scan (called by the scheduled job)
# ---------------------------------------------------------------------------

async def reconcile_library_scan(
    url_validator: Callable[[str], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run a full library reconciliation scan.

    §8.5 contract: each item is an isolated transaction.  One bad item fails
    alone as an Issue; it never blocks or corrupts the rest.

    Returns summary stats.
    """
    from app.db import SessionLocal  # noqa: I001,PLC0415
    from app.models.issue import Issue, IssueSeverity, IssueStatus, IssueType  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415
    from app.storage.journal import recover_stale_journals  # noqa: PLC0415

    stats: dict[str, int] = {
        "items_scanned": 0,
        "items_failed": 0,
        "changes_applied": 0,
        "review_items_created": 0,
        "issues_created": 0,
    }

    # Step 1: recover stale journals
    try:
        async with SessionLocal() as db:
            await recover_stale_journals(db)
            await db.commit()
    except Exception:
        log.exception("reconcile_library_scan: journal recovery failed (non-fatal)")

    # Step 2: load all items (read-only snapshot)
    async with SessionLocal() as db:
        items_result = await db.execute(
            sa.select(Item).join(Library, Library.id == Item.library_id)
            .where(Library.enabled.is_(True))
        )
        item_rows = items_result.scalars().all()
        mode_result = await load_mode_settings(db)

    log.info("reconcile_library_scan: scanning %d item(s)", len(item_rows))

    # Step 3: per-item isolated transaction
    for item_row in item_rows:
        stats["items_scanned"] += 1
        try:
            async with SessionLocal() as db:
                # Reload item in fresh session
                item = await db.get(Item, item_row.id)
                if item is None:
                    continue
                r = await reconcile_one_item(
                    db, item,
                    mode_settings=mode_result,
                    url_validator=url_validator,
                    source="auto",
                )
                await db.commit()
            stats["changes_applied"] += len(r.changes_applied)
            stats["review_items_created"] += len(r.review_items_created)
            stats["issues_created"] += len(r.issues_created)
        except Exception as exc:
            stats["items_failed"] += 1
            log.exception(
                "reconcile_library_scan: item %s failed (isolated; continuing)",
                item_row.id,
            )
            try:
                async with SessionLocal() as db:
                    _issue = Issue(
                        issue_type=IssueType.other,
                        severity=IssueSeverity.warning,
                        status=IssueStatus.open,
                        item_id=item_row.id,
                        detail=f"Reconcile scan error for item {item_row.id}: {exc}",
                        suggested_action="Check the server logs for details.",
                    )
                    db.add(_issue)
                    await db.commit()
            except Exception:
                log.exception(
                    "reconcile_library_scan: could not record issue for item %s",
                    item_row.id,
                )

    # Step 4: scan for orphan directories (dirs with no DB row)
    await _scan_orphan_dirs(mode_result)

    log.info("reconcile_library_scan: done — %s", stats)
    return stats


async def _scan_orphan_dirs(mode_result: dict[str, str]) -> None:
    """Scan library dirs for directories that have no matching Item row."""
    from app.db import SessionLocal  # noqa: I001,PLC0415
    from app.models.issue import Issue, IssueSeverity, IssueStatus, IssueType  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    async with SessionLocal() as db:
        libs_result = await db.execute(
            sa.select(Library).where(Library.enabled.is_(True))
        )
        libraries = libs_result.scalars().all()

        # Build set of known item dir_paths
        known_result = await db.execute(sa.select(Item.dir_path))
        known_dirs: set[str] = {row[0] for row in known_result.all()}

    for lib in libraries:
        mount = Path(lib.mount_path)
        if not mount.is_dir():
            continue
        for shard_dir in sorted(mount.iterdir()):
            if not shard_dir.is_dir():
                continue
            for item_dir in sorted(shard_dir.iterdir()):
                if not item_dir.is_dir():
                    continue
                if str(item_dir) in known_dirs:
                    continue
                # Dir has no matching DB row → orphan
                try:
                    async with SessionLocal() as db:
                        _issue = Issue(
                            issue_type=IssueType.orphan,
                            severity=IssueSeverity.warning,
                            status=IssueStatus.open,
                            item_id=None,
                            detail=f"Directory has no matching DB item: {item_dir}",
                            suggested_action=(
                                "Import the folder via the inbox wizard or delete it if unwanted."
                            ),
                        )
                        db.add(_issue)
                        await db.commit()
                except Exception:
                    log.exception(
                        "reconcile_library_scan: could not record orphan issue for %s",
                        item_dir,
                    )


# ---------------------------------------------------------------------------
# Apply a ReviewItem's proposed_action (called on approve)
# ---------------------------------------------------------------------------

async def apply_review_item_action(
    db: AsyncSession,
    review_item: Any,
    resolved_by_id: int | None = None,
) -> None:
    """Apply the proposed_action of a ReviewItem and write a ChangeLog entry.

    Supports actions: pull_sidecar_to_db, add_file_row, enqueue_render.
    Marks the ReviewItem approved after applying.
    """
    from ..models.change_log import ChangeLog  # noqa: PLC0415
    from ..models.file import File  # noqa: PLC0415
    from ..models.item import Item  # noqa: PLC0415
    from ..models.review_item import ReviewStatus  # noqa: PLC0415
    from ..storage.inventory import infer_role  # noqa: PLC0415

    action = review_item.proposed_action or {}
    behavior = action.get("behavior", "")
    act = action.get("action", "")
    item_id = action.get("item_id")

    summary = f"Approved: {act} (behavior={behavior})"

    if act == "pull_sidecar_to_db" and item_id:
        item_result = await db.execute(select(Item).where(Item.id == item_id))
        item = item_result.scalar_one_or_none()
        if item:
            fields = action.get("fields", {})
            if fields.get("description") is not None:
                item.description = fields["description"]
            if fields.get("source_url") is not None:
                item.source_url = fields["source_url"]
            if fields.get("source_site") is not None:
                item.source_site = fields["source_site"]
            if fields.get("license") is not None:
                item.license = fields["license"]
            item.updated_at = datetime.now(UTC)
            await db.flush()
            summary = f"Sidecar fields pulled to DB for item {item.key!r}."

    elif act == "add_file_row" and item_id:
        file_path = action.get("file_path", "")
        try:
            role = infer_role(file_path)
        except Exception:
            from ..models.file import FileRole  # noqa: PLC0415
            role = FileRole.other
        item_result = await db.execute(select(Item).where(Item.id == item_id))
        item = item_result.scalar_one_or_none()
        if item:
            abs_path = Path(item.dir_path) / file_path
            if abs_path.exists():
                from ..storage.inventory import _mtime_utc, hash_file_sha256  # noqa: I001,PLC0415
                stat = abs_path.stat()
                f = File(
                    item_id=item_id,
                    path=file_path,
                    role=role,
                    size=stat.st_size,
                    sha256=hash_file_sha256(abs_path),
                    mtime=_mtime_utc(stat),
                    last_seen_size=stat.st_size,
                    last_seen_mtime=_mtime_utc(stat),
                )
                db.add(f)
                await db.flush()
                summary = f"File {file_path!r} added to DB for item {item_id}."

    elif act == "enqueue_render" and item_id:
        try:
            from arq import create_pool  # noqa: I001,PLC0415
            from arq.connections import RedisSettings  # noqa: PLC0415
            from app.config import settings  # noqa: PLC0415

            redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            await redis.enqueue_job("render_item", item_id)
            await redis.aclose()
            summary = f"Render enqueued for item {item_id}."
        except Exception:
            log.exception("apply_review_item_action: failed to enqueue render for item %s", item_id)

    # Write ChangeLog
    cl = ChangeLog(
        behavior=behavior,
        change_type=act,
        item_id=item_id,
        summary=summary,
        after_state=action,
        source="review_approved",
    )
    db.add(cl)

    # Mark ReviewItem approved
    review_item.status = ReviewStatus.approved
    review_item.resolved_at = datetime.now(UTC)
    review_item.resolved_by_id = resolved_by_id
    review_item.updated_at = datetime.now(UTC)
    await db.flush()
