"""Import session CRUD endpoints."""
from __future__ import annotations

import logging
import secrets
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from arq.connections import ArqRedis
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
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import csrf_protect, get_current_user, get_db
from ...config import settings
from ...models.import_session import (
    ImportSession,
    ImportSessionFile,
    ImportSessionImage,
    ImportSessionStatus,
    ImportSourceType,
)
from ...models.library import Library
from ...models.user import User

# ``_enqueue_render`` and ``guarded_fetch`` are imported here but unused in this
# module: the commit machinery lives in ``commit.py`` and resolves both through
# this module at call time (``sessions._enqueue_render`` / ``sessions.guarded_fetch``),
# so existing tests that patch them on ``import_sessions.sessions`` keep working.
from ...services.item_helpers import _enqueue_render  # noqa: F401
from ...storage.ssrf_guard import guarded_fetch  # noqa: F401
from ...worker.arq_pool import get_arq_pool
from .helpers import (
    _enqueue_import_job,
    _get_staging_dir,
    _load_session,
    _session_out,
    reconcile_tags,
)
from .schemas import (
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


# Allowed image types/extensions for session-image (viewport-capture) uploads.
_ALLOWED_IMAGE_TYPES: set[str] = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
_ALLOWED_IMAGE_EXTS: set[str] = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_IMAGE_CT_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
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
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
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
            # Log the specific block reason server-side; return a generic message
            # so we don't leak internal-network topology to the importing user.
            log.warning("create_import_session: SSRF-blocked source URL: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="URL is not allowed.",
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
        background_tasks.add_task(_enqueue_import_job, session_id_str, arq)

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


@router.get("/api/import-sessions/{session_id}/files/{filename:path}")
async def serve_session_file(
    session_id: str,
    filename: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Stream a single staged file from an import session's staging directory.

    Used by the in-browser 3D viewer during the import wizard to fetch a staged
    model file (the item does not exist yet, so /api/items/... can't serve it).

    ``filename`` is relative to the session's staging dir (staging is flat, so
    normally just a basename).  Ownership is enforced via ``_load_session``
    (admins may access any session).  Path traversal is refused: the resolved
    path must remain inside the staging dir — mirrors the item download barrier.
    """
    session = await _load_session(session_id, db, user)

    if not session.staging_dir:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session has no staged files.",
        )

    staging_dir = Path(session.staging_dir).resolve()
    # Sanitise: strip any leading slashes so joinpath doesn't override the base.
    clean_path = filename.lstrip("/")
    requested = (staging_dir / clean_path).resolve()

    # Path traversal containment barrier: resolved path must stay inside staging.
    if not requested.is_relative_to(staging_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path (outside staging directory).",
        )

    if not requested.exists() or not requested.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
        )

    return FileResponse(
        path=str(requested),
        filename=requested.name,
        media_type="application/octet-stream",
    )


@router.post(
    "/api/import-sessions/{session_id}/images",
    response_model=ImportSessionOut,
    status_code=status.HTTP_200_OK,
)
async def upload_session_image(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    source: str = Query(default="captured"),
) -> ImportSessionOut:
    """Save a single image onto an import session as an ImportSessionImage row.

    Used by the wizard's "Try to render file" viewport capture (#26): the
    browser renders a staged model in the 3D viewer, grabs a PNG of the current
    view, and POSTs it here.  The image is written into the session's staging
    dir and materialised as a local (is_url=False) session image so it shows in
    the wizard image strip and is carried through to the committed item.

    ``source`` query param: ``captured`` (viewport screenshot, default) or
    ``uploaded`` (plain image upload).  Allowed while the session is still
    editable (pending_wizard / draft / failed).
    """
    session = await _load_session(session_id, db, user)

    if session.status not in (
        ImportSessionStatus.pending_wizard,
        ImportSessionStatus.draft,
        ImportSessionStatus.failed,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot add images to a session in status '{session.status}'.",
        )
    if not session.staging_dir:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Session has no staging area for images.",
        )

    # Validate content-type / extension.
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    suffix = Path(file.filename or "").suffix.lower()
    if content_type not in _ALLOWED_IMAGE_TYPES and suffix not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported image type.  Allowed: png, jpg, jpeg, webp, gif.",
        )

    safe_ext = (
        suffix if suffix in _ALLOWED_IMAGE_EXTS else _IMAGE_CT_TO_EXT.get(content_type, ".png")
    )
    # Unique, traversal-proof filename (never derived from client input).
    is_capture = source == "captured"
    prefix = "capture" if is_capture else "upload"
    safe_filename = f"{prefix}_{secrets.token_hex(8)}{safe_ext}"

    staging = Path(session.staging_dir)
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / safe_filename
    data = await file.read()
    dest.write_bytes(data)

    # Order after all existing images; first image becomes the default.
    order_result = await db.execute(
        select(func.max(ImportSessionImage.order)).where(
            ImportSessionImage.session_id == session.id
        )
    )
    max_order = order_result.scalar_one_or_none()
    new_order = 0 if max_order is None else max_order + 1

    img = ImportSessionImage(
        session_id=session.id,
        path=str(dest),
        is_url=False,
        source="capture" if is_capture else "upload",
        order=new_order,
        is_default=(max_order is None),
    )
    db.add(img)
    session.updated_at = datetime.now(UTC)
    await db.flush()

    # Expire the relationship collections so the reload SELECT re-fetches the
    # freshly-added image (identity-map collections are otherwise stale).
    session_id_pk = session.id
    db.expire(session, ["images", "files"])

    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    result = await db.execute(
        select(ImportSession)
        .options(
            selectinload(ImportSession.files),
            selectinload(ImportSession.images),
        )
        .where(ImportSession.id == session_id_pk)
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
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
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

    background_tasks.add_task(_enqueue_import_job, session_id, arq)

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
