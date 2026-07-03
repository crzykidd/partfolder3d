"""Import session CRUD endpoints."""
from __future__ import annotations

import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import csrf_protect, get_current_user, get_db
from ...config import settings
from ...models.creator import Creator
from ...models.file import File as FileModel
from ...models.image import Image, ImageSource
from ...models.import_session import (
    ImportSession,
    ImportSessionFile,
    ImportSessionImage,
    ImportSessionStatus,
    ImportSourceType,
)
from ...models.item import Item
from ...models.library import Library
from ...models.tag import Tag, TagStatus
from ...models.user import User
from ...services.item_helpers import (
    _attach_tags,
    _enqueue_extract_archives,
    _enqueue_render,
    _update_search_vector,
    _write_item_sidecar,
)
from ...storage.inventory import inventory_item
from ...storage.keys import generate_unique_key
from ...storage.paths import item_dir_path, item_slug, sidecar_name
from .helpers import (
    _enqueue_import_job,
    _ensure_creator,
    _get_staging_dir,
    _load_session,
    _session_out,
    reconcile_tags,
)
from .schemas import (
    BulkCommitRequest,
    BulkCommitResponse,
    BulkCommitSkipped,
    CommitOptions,
    CommitResponse,
    CreateSessionRequest,
    ImportSessionOut,
    PaginatedSessions,
    PatchSessionRequest,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["import"])

# Content-Type → safe file extension map (used for scraped image downloads).
_CT_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _scraped_image_ext(url: str, content_type: str) -> str:
    """Return a safe file extension for a scraped image.

    Priority:
    1. Content-Type header (most reliable — CDN paths like ``format,webp`` have no dot).
    2. URL path suffix after stripping any ``?query`` (e.g. ``.jpg`` in a clean URL).
    3. Fallback: ``.jpg``.
    """
    ct = content_type.split(";")[0].strip().lower()
    if ct in _CT_TO_EXT:
        return _CT_TO_EXT[ct]
    # Try URL path suffix
    url_path = url.split("?")[0]
    suffix = Path(url_path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix if suffix != ".jpeg" else ".jpg"
    return ".jpg"


@router.post(
    "/api/import-sessions",
    response_model=ImportSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_import_session(
    body: CreateSessionRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> ImportSessionOut:
    """Create an import session from a URL or prepare for file upload.

    For source_type='url': immediately enqueues the scrape + pre-fill job.
    For source_type='upload': returns a draft session; use the upload endpoint
    to attach files, then call the process endpoint.
    """
    src = body.source_type.lower()
    if src not in ("url", "upload"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_type must be 'url' or 'upload'",
        )

    if src == "url" and not body.source_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_url is required when source_type='url'",
        )

    # SSRF guard — validate the scrape target URL before persisting or scraping
    if src == "url" and body.source_url:
        from ...storage.ssrf_guard import SSRFBlockedError, assert_safe_url  # noqa: PLC0415

        try:
            assert_safe_url(body.source_url)
        except SSRFBlockedError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Blocked URL: {exc}",
            ) from exc

    # Validate library if provided
    library_id = body.library_id
    if library_id is not None:
        lib_res = await db.execute(
            select(Library).where(Library.id == library_id, Library.enabled.is_(True))
        )
        if lib_res.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {library_id} not found or not enabled.",
            )

    # Create staging dir for upload sessions
    staging_dir: str | None = None
    if src == "upload":
        session_uuid = str(uuid.uuid4())
        staging_path = _get_staging_dir() / session_uuid
        staging_path.mkdir(parents=True, exist_ok=True)
        staging_dir = str(staging_path)

    session = ImportSession(
        status=ImportSessionStatus.draft,
        source_type=ImportSourceType(src),
        source_url=body.source_url,
        suggested_title=body.title,
        confirmed_title=body.title,
        description=body.description,
        license=body.license,
        library_id=library_id,
        staging_dir=staging_dir,
        created_by_id=user.id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # For URL sessions, kick off the import job immediately
    if src == "url":
        session.status = ImportSessionStatus.processing
        await db.flush()
        session_id_str = str(session.id)
        background_tasks.add_task(_enqueue_import_job, session_id_str)

    # Reload with relationships
    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    result = await db.execute(
        select(ImportSession)
        .options(
            selectinload(ImportSession.files),
            selectinload(ImportSession.images),
        )
        .where(ImportSession.id == session.id)
    )
    session = result.scalar_one()
    return _session_out(session)


@router.post(
    "/api/import-sessions/{session_id}/files",
    response_model=ImportSessionOut,
    status_code=status.HTTP_200_OK,
)
async def upload_session_files(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    files: list[UploadFile] = File(...),
) -> ImportSessionOut:
    """Upload files to a draft upload-type import session.

    Files are saved to the session's staging_dir.  Allowed in draft status only.
    After uploading, call POST /api/import-sessions/{id}/process to kick off pre-fill.
    """
    session = await _load_session(session_id, db, user)

    if session.status != ImportSessionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Files can only be uploaded to a 'draft' session.",
        )
    if session.source_type != ImportSourceType.upload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File upload only supported for source_type='upload'.",
        )
    if not session.staging_dir:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session has no staging_dir.",
        )

    staging = Path(session.staging_dir)
    staging.mkdir(parents=True, exist_ok=True)

    # Infer roles
    from ...storage.inventory import infer_role  # noqa: PLC0415

    for upload in files:
        filename = (upload.filename or "file").replace("/", "_").replace("..", "_")
        dest = staging / filename
        data = await upload.read()
        dest.write_bytes(data)
        role = infer_role(filename).value

        sf = ImportSessionFile(
            session_id=session.id,
            staged_path=str(dest),
            original_name=filename,
            role=role,
            size=len(data),
        )
        db.add(sf)

    session.updated_at = datetime.now(UTC)
    await db.flush()

    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    result = await db.execute(
        select(ImportSession)
        .options(
            selectinload(ImportSession.files),
            selectinload(ImportSession.images),
        )
        .where(ImportSession.id == session.id)
    )
    return _session_out(result.scalar_one())


@router.post(
    "/api/import-sessions/{session_id}/process",
    response_model=ImportSessionOut,
    status_code=status.HTTP_200_OK,
)
async def process_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> ImportSessionOut:
    """Kick off the import processing job for a draft session.

    This transitions the session from 'draft' to 'processing' and enqueues
    the worker task that scrapes / reads the sidecar / reconciles tags.
    """
    session = await _load_session(session_id, db, user)

    if session.status != ImportSessionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot process a session in status '{session.status}'.",
        )

    session.status = ImportSessionStatus.processing
    session.updated_at = datetime.now(UTC)
    await db.flush()

    background_tasks.add_task(_enqueue_import_job, session_id)

    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    result = await db.execute(
        select(ImportSession)
        .options(
            selectinload(ImportSession.files),
            selectinload(ImportSession.images),
        )
        .where(ImportSession.id == session.id)
    )
    return _session_out(result.scalar_one())


@router.get("/api/import-sessions", response_model=PaginatedSessions)
async def list_import_sessions(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    all_users: bool = Query(default=False, description="Admin: list all users' sessions"),
) -> PaginatedSessions:
    """List import sessions (own sessions; admin can request all_users=true)."""
    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    from ...models.user import UserRole  # noqa: PLC0415

    query = select(ImportSession).options(
        selectinload(ImportSession.files),
        selectinload(ImportSession.images),
    )

    is_admin = user.role == UserRole.admin
    if not is_admin or not all_users:
        query = query.where(ImportSession.created_by_id == user.id)

    if status_filter:
        query = query.where(ImportSession.status == status_filter)

    # Exclude committed/cancelled by default unless explicitly filtered
    if not status_filter:
        query = query.where(
            ImportSession.status.in_([
                ImportSessionStatus.draft,
                ImportSessionStatus.processing,
                ImportSessionStatus.pending_wizard,
                ImportSessionStatus.failed,
            ])
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            query.order_by(ImportSession.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
    ).scalars().all()

    return PaginatedSessions(
        total=total,
        page=page,
        per_page=per_page,
        sessions=[_session_out(s) for s in rows],
    )


@router.get("/api/import-sessions/{session_id}", response_model=ImportSessionOut)
async def get_import_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImportSessionOut:
    """Get an import session by ID."""
    session = await _load_session(session_id, db, user)
    return _session_out(session)


@router.patch("/api/import-sessions/{session_id}", response_model=ImportSessionOut)
async def patch_import_session(
    session_id: str,
    body: PatchSessionRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImportSessionOut:
    """Update wizard fields on a session (title, tags, creator, etc.).

    Allowed in: pending_wizard, draft.
    """
    session = await _load_session(session_id, db, user)

    if session.status not in (
        ImportSessionStatus.pending_wizard,
        ImportSessionStatus.draft,
        ImportSessionStatus.failed,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot patch a session in status '{session.status}'.",
        )

    if body.confirmed_title is not None:
        session.confirmed_title = body.confirmed_title
    if body.description is not None:
        session.description = body.description
    if body.license is not None:
        session.license = body.license
    if body.source_url is not None:
        session.source_url = body.source_url
    if body.creator_name is not None:
        session.creator_name = body.creator_name
    if body.creator_profile_url is not None:
        session.creator_profile_url = body.creator_profile_url
    if body.creator_source_site is not None:
        session.creator_source_site = body.creator_source_site
    if body.creator_is_own_design is not None:
        session.creator_is_own_design = body.creator_is_own_design
    if body.default_image_path is not None:
        session.default_image_path = body.default_image_path
        # Sync is_default flags on the session's ImportSessionImage rows so the
        # commit handler (which reads si.is_default) sees the correct default.
        # Use clear-all-then-set-one — same pattern as delete_import_session_image.
        imgs_result = await db.execute(
            select(ImportSessionImage).where(
                ImportSessionImage.session_id == session.id
            )
        )
        session_imgs = imgs_result.scalars().all()
        matched = False
        for img in session_imgs:
            if img.path == body.default_image_path:
                img.is_default = True
                matched = True
            else:
                img.is_default = False
        if not matched:
            # Sanitize CR/LF before logging a user-provided value (CodeQL
            # py/log-injection); match the escaping used elsewhere in this package.
            _safe_default = body.default_image_path.replace("\r", "\\r").replace(
                "\n", "\\n"
            )
            log.debug(
                "patch_import_session: default_image_path %r has no matching image row yet",
                _safe_default,
            )
    if body.library_id is not None:
        session.library_id = body.library_id

    # User has confirmed the final tag list
    if body.confirmed_tags is not None:
        reconciled = await reconcile_tags(db, body.confirmed_tags)
        # Keep any user-typed tags that weren't in the original reconciliation
        # as pending (they'll go through the approval queue)
        existing_pending = (
            session.tag_state.get("pending", []) if session.tag_state else []
        )
        all_pending = list(set(reconciled["pending"] + existing_pending))
        session.tag_state = {
            "confirmed": reconciled["confirmed"],
            "pending": all_pending,
        }

    session.updated_at = datetime.now(UTC)
    await db.flush()

    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    result = await db.execute(
        select(ImportSession)
        .options(
            selectinload(ImportSession.files),
            selectinload(ImportSession.images),
        )
        .where(ImportSession.id == session.id)
    )
    return _session_out(result.scalar_one())


async def _resolve_import_library(
    override_lib_id: int | None,
    session_lib_id: int | None,
    db: AsyncSession,
) -> Library | None:
    """Resolve which enabled library to use for a session commit.

    Resolution order (first match wins, only enabled libraries are valid):
      (a) override_lib_id  — explicit caller override (bulk-commit body)
      (b) session_lib_id   — library already set on the session
      (c) import.default_library_id setting
      (d) sole enabled library (exactly one)
      (e) None             — caller must skip/report
    """
    import json as _json  # noqa: PLC0415

    from ...models.setting import Setting  # noqa: PLC0415

    async def _get_enabled(lib_id: int) -> Library | None:
        res = await db.execute(
            select(Library).where(Library.id == lib_id, Library.enabled.is_(True))
        )
        return res.scalar_one_or_none()

    # (a) explicit override
    if override_lib_id is not None:
        return await _get_enabled(override_lib_id)

    # (b) session's own library_id
    if session_lib_id is not None:
        lib = await _get_enabled(session_lib_id)
        if lib is not None:
            return lib

    # (c) default import library setting
    setting_res = await db.execute(
        select(Setting).where(Setting.key == "import.default_library_id")
    )
    setting_row = setting_res.scalar_one_or_none()
    if setting_row is not None:
        try:
            raw_id = _json.loads(setting_row.value)
            if isinstance(raw_id, int):
                lib = await _get_enabled(raw_id)
                if lib is not None:
                    return lib
        except Exception:
            pass

    # (d) sole enabled library
    all_libs_res = await db.execute(select(Library).where(Library.enabled.is_(True)))
    all_libs = all_libs_res.scalars().all()
    if len(all_libs) == 1:
        return all_libs[0]

    return None


async def _commit_session_inner(
    session: ImportSession,
    library: Library,
    user: User,
    db: AsyncSession,
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
            tag = Tag(name=tag_name, status=TagStatus.pending)
            db.add(tag)
            await db.flush()
        if tag_name not in confirmed_tags:
            confirmed_tags.append(tag_name)

    if confirmed_tags:
        await _attach_tags(db, item, confirmed_tags, new_tag_status=TagStatus.pending)

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
    img_order = 0
    for si in session.images:
        if si.is_url:
            try:
                import httpx as _httpx  # noqa: PLC0415

                images_dir = item_dir / "images"
                images_dir.mkdir(exist_ok=True)
                with _httpx.Client(timeout=settings.SCRAPE_TIMEOUT) as c:
                    r = c.get(si.path, follow_redirects=True)
                    if r.status_code == 200:
                        ext = _scraped_image_ext(
                            si.path,
                            r.headers.get("content-type", ""),
                        )
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
            except Exception:
                log.warning("commit: failed to download image %s", si.path)
        else:
            rel = Path(si.path).name
            img_path = item_dir / rel
            if img_path.exists():
                if si.path.startswith("images/"):
                    rel_path = si.path
                else:
                    rel_path = str(Path("images") / rel)
                img_obj = Image(
                    item_id=item.id,
                    path=rel_path,
                    source=ImageSource.uploaded,
                    is_default=si.is_default,
                    order=img_order,
                )
                db.add(img_obj)
                img_order += 1

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

    # ---- 13. Enqueue render (fire-and-forget) ----
    if render != "off":
        await _enqueue_render(item.id)

    # ---- 14. Enqueue ZIP extraction when the item contains any ZIP ----
    from ...models.file import FileRole as _FileRole  # noqa: PLC0415
    has_zip = any(rec.role == _FileRole.zip for rec in records)
    if has_zip:
        await _enqueue_extract_archives(item.id)

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
        return await _commit_session_inner(session, library, user, db, render=render_pref)

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
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Commit failed: {exc}",
        ) from exc


@router.post("/api/import-sessions/bulk-commit", response_model=BulkCommitResponse)
async def bulk_commit_import_sessions(
    body: BulkCommitRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
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

                await _commit_session_inner(session_obj, library, user, iso_db, render=body.render)
                await iso_db.commit()
                committed_count += 1

            except Exception as exc:
                log.exception("bulk_commit: error on session %s", sid)
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


@router.post(
    "/api/import-sessions/{session_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def cancel_import_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Discard an import session and clean up its staging area."""
    session = await _load_session(session_id, db, user)

    if session.status in (ImportSessionStatus.committed,):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot cancel a committed session.",
        )

    # Clean up staging dir
    if session.staging_dir:
        staging_path = Path(session.staging_dir)
        if staging_path.is_dir():
            try:
                shutil.rmtree(str(staging_path))
            except Exception:
                log.warning("cancel: failed to clean staging dir %s", staging_path)

    session.status = ImportSessionStatus.cancelled
    session.updated_at = datetime.now(UTC)
    await db.flush()


@router.delete(
    "/api/import-sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_import_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Permanently delete an import session and clean up its staging area.

    Removes the ImportSession row (cascading to ImportSessionImage /
    ImportSessionFile) and best-effort removes the staging_dir if it exists
    under DATA_DIR.

    Does NOT touch any committed Item or library files.
    Returns 204 on success; 404 if the session is not found or not owned.
    """
    session = await _load_session(session_id, db, user)

    # Best-effort: remove staging dir — only under DATA_DIR, never item dirs
    if session.staging_dir:
        staging_path = Path(session.staging_dir)
        if staging_path.is_dir():
            try:
                staging_path.relative_to(Path(settings.DATA_DIR))
                shutil.rmtree(str(staging_path))
            except ValueError:
                log.warning(
                    "delete_session: staging_dir %s is outside DATA_DIR — skipping removal",
                    staging_path,
                )
            except Exception:
                log.warning(
                    "delete_session: failed to clean staging dir %s", staging_path
                )

    await db.delete(session)
    await db.flush()


@router.delete(
    "/api/import-sessions/{session_id}/images/{image_id}",
    response_model=ImportSessionOut,
    status_code=status.HTTP_200_OK,
)
async def delete_import_session_image(
    session_id: str,
    image_id: int,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImportSessionOut:
    """Remove an image from an import session.

    Deletes the ImportSessionImage row and best-effort removes the local staged
    file if it lives inside the session's staging_dir.  For scraped URL images
    (is_url=True) only the row is dropped — there is no local file.

    If the deleted image was the default, reassigns is_default to the first
    remaining image (lowest order) and updates default_image_path on the
    session, or clears default_image_path when no images remain.

    Returns the updated session.
    404 if the image doesn't exist or doesn't belong to this session.
    """
    session = await _load_session(session_id, db, user)

    # Verify the image belongs to this session
    img_result = await db.execute(
        select(ImportSessionImage).where(
            ImportSessionImage.id == image_id,
            ImportSessionImage.session_id == session.id,
        )
    )
    img = img_result.scalar_one_or_none()
    if img is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found in this session.",
        )

    was_default = img.is_default
    img_path = img.path
    img_is_url = img.is_url

    # Delete the image row
    await db.delete(img)
    await db.flush()

    # Reassign default to the first remaining image if we just removed the default
    if was_default:
        remaining_result = await db.execute(
            select(ImportSessionImage)
            .where(ImportSessionImage.session_id == session.id)
            .order_by(ImportSessionImage.order)
            .limit(1)
        )
        first_remaining = remaining_result.scalar_one_or_none()
        if first_remaining is not None:
            first_remaining.is_default = True
            session.default_image_path = first_remaining.path
        else:
            session.default_image_path = None
        await db.flush()

    # Best-effort: remove local staged file (skip URL images)
    if not img_is_url and session.staging_dir:
        try:
            file_path = Path(img_path)
            staging_path = Path(session.staging_dir)
            # Only remove if the file is inside the staging dir
            file_path.relative_to(staging_path)
            if file_path.is_file():
                file_path.unlink()
        except ValueError:
            pass  # file is not under staging_dir — don't touch it
        except Exception:
            log.warning(
                "delete_session_image: could not remove staged file %s", img_path
            )

    session.updated_at = datetime.now(UTC)
    await db.flush()

    # Expire only the relationship collections so the reload SELECT re-fetches
    # fresh data from the DB.  We must capture session.id before expiring to
    # avoid triggering lazy-load on the scalar PK column.
    session_id = session.id
    db.expire(session, ["images", "files"])

    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    result = await db.execute(
        select(ImportSession)
        .options(
            selectinload(ImportSession.files),
            selectinload(ImportSession.images),
        )
        .where(ImportSession.id == session_id)
    )
    return _session_out(result.scalar_one())
