"""Import session commit machinery.

Extracted from ``sessions.py`` (audit §D) — holds the commit core
(``_commit_session_inner``) and the ``commit`` / ``bulk-commit`` endpoints.
The endpoints live on this module's ``router``; the package ``__init__`` includes
it so their paths/methods are unchanged.

Two symbols are deliberately reached through the ``sessions`` module rather than
imported directly:

  * ``guarded_fetch`` — tests patch ``import_sessions.sessions.guarded_fetch``.
  * ``_enqueue_render`` — tests monkeypatch it on the ``sessions`` module.

Resolving them via ``_sessions.<name>`` at call time keeps those existing patches
effective after the split.  ``_resolve_import_library`` and ``_scraped_image_ext``
stay defined in ``sessions.py`` (tests import them from there) and are re-used here.
"""
from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import csrf_protect, get_current_user, get_db
from ...config import settings
from ...models.creator import Creator
from ...models.file import File as FileModel
from ...models.image import Image, ImageSource
from ...models.import_session import (
    ImportSession,
    ImportSessionStatus,
    ImportSourceType,
)
from ...models.item import Item
from ...models.library import Library
from ...models.tag import Tag, TagStatus
from ...models.user import User
from ...services.item_helpers import (
    _attach_tags,
    _enqueue_analyze,
    _enqueue_extract_archives,
    _update_search_vector,
    _write_item_sidecar,
)
from ...services.settings_service import get_tags_auto_approve
from ...storage.inventory import inventory_item
from ...storage.keys import generate_unique_key
from ...storage.paths import item_dir_path, item_slug, sidecar_name
from ...storage.ssrf_guard import (
    GuardedFetchError,
    SSRFBlockedError,
    sanitize_for_log,
)
from ...worker.arq_pool import get_arq_pool
from . import sessions as _sessions
from .helpers import _ensure_creator, _load_session
from .schemas import (
    BulkCommitRequest,
    BulkCommitResponse,
    BulkCommitSkipped,
    CommitOptions,
    CommitResponse,
)
from .sessions import _resolve_import_library, _scraped_image_ext

log = logging.getLogger(__name__)

router = APIRouter(tags=["import"])


async def _commit_session_inner(
    session: ImportSession,
    library: Library,
    user: User,
    db: AsyncSession,
    pool: ArqRedis,
    render: str = "auto",
) -> CommitResponse:
    """Core commit logic shared by single-commit and bulk-commit paths.

    Expects `session` and `library` already loaded from `db`.  Caller is
    responsible for the surrounding transaction (commit / rollback on error).

    render: "auto" → enqueue server render (still gated by instance render.mode);
            "off"  → skip _enqueue_render entirely for this commit.
    """
    session_id_str = str(session.id)
    title = session.confirmed_title or session.suggested_title

    # ---- 1. Resolve/create creator ----
    creator: Creator | None = None
    if session.creator_is_own_design:
        creator = await _ensure_creator(
            db,
            name=user.name,
            user_id=user.id,
        )
    elif session.creator_name:
        creator = await _ensure_creator(
            db,
            name=session.creator_name,
            profile_url=session.creator_profile_url,
            source_site=session.creator_source_site,
        )

    # ---- 2. Generate key + build item dir path ----
    key = await generate_unique_key(db)
    slug = item_slug(title, key)  # type: ignore[arg-type]
    item_dir = item_dir_path(library.mount_path, key, title)  # type: ignore[arg-type]
    item_dir.mkdir(parents=True, exist_ok=True)

    # ---- 3. Move staged files into item dir ----
    for sf in session.files:
        src_path = Path(sf.staged_path)
        if src_path.exists():
            dest_path = item_dir / src_path.name
            try:
                src_path.replace(dest_path)
            except OSError:
                shutil.copy2(str(src_path), str(dest_path))
                src_path.unlink(missing_ok=True)

    # For inbox sessions: move files from inbox folder too
    if session.source_type == ImportSourceType.inbox and session.inbox_folder:
        inbox_path = Path(session.inbox_folder)
        if inbox_path.is_dir():
            for entry in inbox_path.iterdir():
                if entry.is_file():
                    dest = item_dir / entry.name
                    try:
                        entry.replace(dest)
                    except OSError:
                        shutil.copy2(str(entry), str(dest))
                        entry.unlink(missing_ok=True)

    # ---- 4. Insert Item row ----
    item = Item(
        key=key,
        title=title,
        slug=slug,
        description=session.description,
        source_url=session.source_url,
        source_site=session.source_site,
        license=session.license,
        creator_id=creator.id if creator else None,
        library_id=library.id,
        dir_path=str(item_dir),
        schema_version=1,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)

    # ---- 5. Attach tags ----
    # When the instance-wide auto-approve setting (#31) is on, brand-new tags land
    # ``active`` (skipping the admin approval queue); otherwise they enter as
    # ``pending`` exactly as before.  This only affects tags first created here —
    # existing tags are matched/reused regardless of their status.
    new_tag_status = (
        TagStatus.active if await get_tags_auto_approve(db) else TagStatus.pending
    )
    confirmed_tags: list[str] = []
    pending_tags: list[str] = []
    if session.tag_state:
        confirmed_tags = session.tag_state.get("confirmed", [])
        pending_tags = session.tag_state.get("pending", [])

    for tag_name in pending_tags:
        tag_name = tag_name.strip()
        if not tag_name:
            continue
        t_res = await db.execute(select(Tag).where(Tag.name == tag_name))
        tag = t_res.scalar_one_or_none()
        if tag is None:
            tag = Tag(name=tag_name, status=new_tag_status)
            db.add(tag)
            await db.flush()
        if tag_name not in confirmed_tags:
            confirmed_tags.append(tag_name)

    if confirmed_tags:
        await _attach_tags(db, item, confirmed_tags, new_tag_status=new_tag_status)

    # ---- 6. Inventory files + create File rows ----
    sc_name = sidecar_name(title, key)  # type: ignore[arg-type]
    records = inventory_item(item_dir, sc_name)
    for rec in records:
        f = FileModel(
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

    # ---- 6b. Capture source_baseline ----
    if session.source_url:
        from ...models.file import FileRole  # noqa: PLC0415
        baseline: dict[str, str] = {}
        for rec in records:
            if rec.role == FileRole.model and rec.sha256:
                baseline[rec.relative_path] = rec.sha256
        item.source_baseline = baseline if baseline else None
    await db.flush()

    # ---- 7. Handle images ----
    # Defensive fallback (issue #14): if PATCH set default_image_path before the
    # image rows were materialized, no ImportSessionImage has is_default=True.
    # Honor default_image_path here so the created item still gets a default.
    # (Restored after the commit path was refactored into _commit_session_inner.)
    if session.default_image_path and not any(si.is_default for si in session.images):
        sorted_imgs = sorted(session.images, key=lambda x: x.order)
        matched = next(
            (si for si in sorted_imgs if si.path == session.default_image_path), None
        )
        if matched is not None:
            matched.is_default = True
        elif sorted_imgs:
            sorted_imgs[0].is_default = True

    img_order = 0
    for si in session.images:
        if si.is_url:
            _safe_img_url = sanitize_for_log(si.path)
            try:
                # Guarded fetch: SSRF-checked (scheme + DNS + IP per hop, no
                # auto-redirect), image/* content-type enforced, body streamed
                # and aborted past the size cap.  A per-image failure skips that
                # image only — it must not crash the whole commit.
                images_dir = item_dir / "images"
                images_dir.mkdir(exist_ok=True)
                r = _sessions.guarded_fetch(
                    si.path,
                    max_bytes=settings.SCRAPE_IMAGE_MAX_MB * 1024 * 1024,
                    timeout=settings.SCRAPE_TIMEOUT,
                    allowed_content_types=("image/",),
                )
                if r.status_code == 200:
                    ext = _scraped_image_ext(si.path, r.content_type)
                    img_name = f"scraped_{img_order:02d}{ext}"
                    img_dest = images_dir / img_name
                    img_dest.write_bytes(r.content)
                    rel_path = str(img_dest.relative_to(item_dir))
                    img_obj = Image(
                        item_id=item.id,
                        path=rel_path,
                        source=ImageSource.scraped,
                        is_default=si.is_default,
                        order=img_order,
                    )
                    db.add(img_obj)
                    img_order += 1
                else:
                    log.warning(
                        "commit: image fetch returned HTTP %s for %s",
                        r.status_code, _safe_img_url,
                    )
            except (SSRFBlockedError, GuardedFetchError) as exc:
                log.warning(
                    "commit: blocked/failed image %s: %s", _safe_img_url, exc
                )
            except Exception:
                log.warning("commit: failed to download image %s", _safe_img_url)
        else:
            # Local (is_url=False) session image — e.g. a wizard viewport
            # capture (#26) staged in the session's staging dir.  Locate the
            # source bytes (prefer the staged absolute path; fall back to a file
            # already sitting in the item dir), copy into images/, and record a
            # matching images/<name> Image row.
            rel = Path(si.path).name
            src = Path(si.path)
            src_file: Path | None = None
            if src.is_absolute() and src.is_file():
                src_file = src
            elif (item_dir / rel).exists():
                src_file = item_dir / rel

            if src_file is not None:
                images_dir = item_dir / "images"
                images_dir.mkdir(exist_ok=True)
                dest = images_dir / rel
                if src_file.resolve() != dest.resolve():
                    shutil.copy2(str(src_file), str(dest))
                rel_path = str(dest.relative_to(item_dir))
                img_source = (
                    ImageSource.captured
                    if si.source == "capture"
                    else ImageSource.uploaded
                )
                img_obj = Image(
                    item_id=item.id,
                    path=rel_path,
                    source=img_source,
                    is_default=si.is_default,
                    order=img_order,
                )
                db.add(img_obj)
                img_order += 1

    await db.flush()

    # ---- 7b. Re-inventory so the images just written show in the file list ----
    # inventory_item ran in step 6, BEFORE the scraped/uploaded images were written to
    # images/, so those files got Image rows (thumbnails) but no File rows — the file
    # list only caught up on the next reconcile scan / manual rescan. Re-inventory now
    # and add File rows for anything new, matching exactly what a rescan produces.
    _existing_paths = {rec.relative_path for rec in records}
    records = inventory_item(item_dir, sc_name)
    for rec in records:
        if rec.relative_path in _existing_paths:
            continue
        db.add(
            FileModel(
                item_id=item.id,
                path=rec.relative_path,
                role=rec.role,
                size=rec.size,
                sha256=rec.sha256,
                mtime=rec.mtime,
                last_seen_size=rec.size,
                last_seen_mtime=rec.mtime,
            )
        )
    await db.flush()

    # ---- 8. Set creator on item for sidecar ----
    if creator:
        await db.refresh(creator)
        item.creator = creator

    # ---- 9. Write sidecar ----
    await _write_item_sidecar(db, item)

    # ---- 10. Update FTS vector ----
    await _update_search_vector(
        db, item.id, item.title, item.description, confirmed_tags
    )

    # ---- 11. Update session status ----
    session.status = ImportSessionStatus.committed
    session.item_id = item.id
    session.updated_at = datetime.now(UTC)
    await db.flush()

    # ---- 12. Clean up staging dir ----
    if session.staging_dir:
        staging_path = Path(session.staging_dir)
        if staging_path.is_dir():
            try:
                shutil.rmtree(str(staging_path))
            except Exception:
                log.warning("commit: failed to clean staging dir %s", staging_path)

    # ---- 13. Enqueue render + analyze (fire-and-forget) ----
    # Pass db so a queued Job row is written now — makes a bulk-import backlog
    # visible in the Jobs UI before any worker starts (#20).
    if render != "off":
        await _sessions._enqueue_render(item.id, pool=pool, db=db)
    # Analyze runs regardless of render.mode (slice/mesh metadata, 3MF thumbnails).
    # Without this, an imported item with no ZIP was never analyzed until a manual
    # rescan — every other create/upload/rescan path already enqueues it.
    await _enqueue_analyze(item.id, pool=pool, db=db)

    # ---- 14. Enqueue ZIP extraction when the item contains any ZIP ----
    from ...models.file import FileRole as _FileRole  # noqa: PLC0415
    has_zip = any(rec.role == _FileRole.zip for rec in records)
    if has_zip:
        await _enqueue_extract_archives(item.id, pool=pool, db=db)

    return CommitResponse(
        item_key=item.key,
        item_id=item.id,
        session_id=session_id_str,
    )


@router.post("/api/import-sessions/{session_id}/commit", response_model=CommitResponse)
async def commit_import_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
    body: CommitOptions | None = None,
) -> CommitResponse:
    """Finalize an import session into a real Item.

    Reuses the same path as create_item: assigns storage path from confirmed title,
    moves staged/inbox files into the library via the atomic-move journal, attaches
    tags + creator + images, writes the sidecar, enqueues the render job.

    The session must be in 'pending_wizard' status and have a confirmed_title and
    library_id set.  On failure, the session is marked 'failed' and no partial item
    is created.

    Optional body: CommitOptions with render="auto"|"off" (default "auto").
    Omitting the body preserves existing behavior.
    """
    session = await _load_session(session_id, db, user)

    if session.status != ImportSessionStatus.pending_wizard:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Session must be in 'pending_wizard' status to commit "
                f"(current: '{session.status}')."
            ),
        )

    title = session.confirmed_title or session.suggested_title
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="confirmed_title must be set before committing.",
        )

    # Resolve library: session's own library_id (override or sole-lib fallback)
    library = await _resolve_import_library(None, session.library_id, db)
    if library is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "library_id must be set (or a default import library configured) "
                "before committing."
            ),
        )

    render_pref = body.render if body else "auto"

    try:
        return await _commit_session_inner(session, library, user, db, arq, render=render_pref)

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("commit_import_session: failed for session %s", session_id)
        try:
            session.status = ImportSessionStatus.failed
            session.error = str(exc)
            session.updated_at = datetime.now(UTC)
            await db.flush()
        except Exception:
            log.debug(
                "commit_import_session: best-effort failed-status flush failed for session %s",
                session_id,
                exc_info=True,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Commit failed.",
        ) from exc


@router.post("/api/import-sessions/bulk-commit", response_model=BulkCommitResponse)
async def bulk_commit_import_sessions(
    body: BulkCommitRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> BulkCommitResponse:
    """Commit multiple pending_wizard import sessions in one call.

    For each targeted session the commit runs in its own isolated transaction
    so a failure on one does not roll back others (partial-success).

    Library resolution order per session:
      (a) body.library_id override if provided
      (b) session's own library_id if set
      (c) import.default_library_id instance setting
      (d) sole enabled library
      (e) skip with reason "no_library"

    Returns:
      { total, committed, skipped: [{session_id, reason}], errors: [{session_id, reason}] }
    """
    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    from ...db import SessionLocal  # noqa: PLC0415
    from ...models.user import UserRole  # noqa: PLC0415

    is_admin = user.role == UserRole.admin

    # ---- 1. Determine target session IDs ----
    if body.session_ids is not None:
        # Explicit list: load each session (ownership enforced per-session below)
        target_ids: list[str] = body.session_ids
    else:
        # All pending_wizard sessions visible to this user
        q = (
            select(ImportSession.id)
            .where(ImportSession.status == ImportSessionStatus.pending_wizard)
        )
        if not is_admin:
            q = q.where(ImportSession.created_by_id == user.id)
        rows = (await db.execute(q)).scalars().all()
        target_ids = [str(r) for r in rows]

    committed_count = 0
    skipped: list[BulkCommitSkipped] = []
    errors: list[BulkCommitSkipped] = []

    # ---- 2. Process each session in its own transaction ----
    for sid in target_ids:
        async with SessionLocal() as iso_db:
            try:
                import uuid as _uuid  # noqa: PLC0415

                try:
                    sid_uuid = _uuid.UUID(sid)
                except ValueError:
                    skipped.append(BulkCommitSkipped(session_id=sid, reason="invalid_id"))
                    continue

                result = await iso_db.execute(
                    select(ImportSession)
                    .options(
                        selectinload(ImportSession.files),
                        selectinload(ImportSession.images),
                    )
                    .where(ImportSession.id == sid_uuid)
                )
                session_obj = result.scalar_one_or_none()

                if session_obj is None:
                    skipped.append(BulkCommitSkipped(session_id=sid, reason="not_found"))
                    continue

                # Ownership check
                if not is_admin and session_obj.created_by_id != user.id:
                    skipped.append(BulkCommitSkipped(session_id=sid, reason="forbidden"))
                    continue

                # Status check
                if session_obj.status != ImportSessionStatus.pending_wizard:
                    skipped.append(
                        BulkCommitSkipped(
                            session_id=sid,
                            reason=f"wrong_status:{session_obj.status.value}",
                        )
                    )
                    continue

                # Title check
                title = session_obj.confirmed_title or session_obj.suggested_title
                if not title:
                    skipped.append(BulkCommitSkipped(session_id=sid, reason="no_title"))
                    continue

                # Library resolution
                library = await _resolve_import_library(
                    body.library_id, session_obj.library_id, iso_db
                )
                if library is None:
                    skipped.append(BulkCommitSkipped(session_id=sid, reason="no_library"))
                    continue

                await _commit_session_inner(
                    session_obj, library, user, iso_db, arq, render=body.render
                )
                await iso_db.commit()
                committed_count += 1

            except Exception as exc:
                # Sanitize CR/LF before logging the user-provided session id
                # (CodeQL py/log-injection); session_ids is list[str].
                _safe_sid = sid.replace("\r", "\\r").replace("\n", "\\n")
                log.exception("bulk_commit: error on session %s", _safe_sid)
                try:
                    await iso_db.rollback()
                except Exception:
                    pass
                errors.append(
                    BulkCommitSkipped(session_id=sid, reason=str(exc)[:200])
                )

    return BulkCommitResponse(
        total=len(target_ids),
        committed=committed_count,
        skipped=skipped,
        errors=errors,
    )
