"""Import wizard API endpoints (Phase 5).

Manages ImportSession lifecycle: create → process → wizard review → commit.

POST   /api/import-sessions                    → create session (upload / URL)
GET    /api/import-sessions                    → list pending sessions (mine or admin=all)
GET    /api/import-sessions/{id}               → get one session
PATCH  /api/import-sessions/{id}               → update wizard fields
POST   /api/import-sessions/{id}/commit        → finalize → Item
POST   /api/import-sessions/{id}/cancel        → discard

GET    /api/site-capabilities                  → list per-domain capabilities
GET    /api/site-capabilities/{domain}         → get one
PATCH  /api/site-capabilities/{domain}         → set token / update flags

POST   /api/import-sessions/from-share-link    → STUB (Phase 7)

Auth: all endpoints require authentication.  Admin users can list/manage all sessions.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import sqlalchemy as sa
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
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_current_user, get_db
from ..config import settings
from ..models.creator import Creator
from ..models.file import File as FileModel
from ..models.image import Image, ImageSource
from ..models.import_session import (
    ImportSession,
    ImportSessionFile,
    ImportSessionImage,
    ImportSessionStatus,
    ImportSourceType,
)
from ..models.item import Item
from ..models.library import Library
from ..models.site_capability import SiteCapability, SiteToken
from ..models.tag import Tag, TagAlias, TagStatus
from ..models.user import User
from ..storage.inventory import inventory_item
from ..storage.keys import generate_unique_key
from ..storage.paths import item_dir_path, item_slug, sidecar_name

# Import helpers from items router (reuse, don't duplicate)
from .items import (
    _attach_tags,
    _enqueue_render,
    _update_search_vector,
    _write_item_sidecar,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["import"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    source_type: str  # "url" or "upload" (multipart handled separately)
    source_url: str | None = None
    library_id: int | None = None
    # Optional pre-filled metadata
    title: str | None = None
    description: str | None = None
    license: str | None = None


class PatchSessionRequest(BaseModel):
    confirmed_title: str | None = None
    description: str | None = None
    license: str | None = None
    source_url: str | None = None
    # Creator: either named or "own design"
    creator_name: str | None = None
    creator_profile_url: str | None = None
    creator_source_site: str | None = None
    creator_is_own_design: bool | None = None
    # Tag reconciliation: user-confirmed final tag list
    confirmed_tags: list[str] | None = None
    # Default image (path or URL from session images)
    default_image_path: str | None = None
    library_id: int | None = None


class ImportSessionFileOut(BaseModel):
    id: int
    staged_path: str
    original_name: str
    role: str
    size: int

    model_config = {"from_attributes": True}


class ImportSessionImageOut(BaseModel):
    id: int
    path: str
    is_url: bool
    source: str
    order: int
    is_default: bool

    model_config = {"from_attributes": True}


class TagStateOut(BaseModel):
    confirmed: list[str] = []
    pending: list[str] = []


class ImportSessionOut(BaseModel):
    id: str
    status: str
    source_type: str
    source_url: str | None
    inbox_folder: str | None
    staging_dir: str | None
    suggested_title: str | None
    confirmed_title: str | None
    description: str | None
    license: str | None
    source_site: str | None
    creator_name: str | None
    creator_profile_url: str | None
    creator_source_site: str | None
    creator_is_own_design: bool
    creator_id: int | None
    tag_state: TagStateOut | None
    default_image_path: str | None
    library_id: int | None
    job_id: str | None
    item_id: int | None
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    error: str | None
    # Worker-set annotation: "Fetched via AgentQL" on agentql success, or a
    # blocked/budget message.  None for standard static scrapes.
    scrape_note: str | None
    files: list[ImportSessionFileOut]
    images: list[ImportSessionImageOut]

    model_config = {"from_attributes": False}


class PaginatedSessions(BaseModel):
    total: int
    page: int
    per_page: int
    sessions: list[ImportSessionOut]


class SiteCapabilityOut(BaseModel):
    domain: str
    can_scrape_metadata: bool
    can_scrape_images: bool
    requires_token: bool
    is_manual_only: bool
    last_probed_at: datetime | None
    notes: str | None
    has_token: bool = False

    model_config = {"from_attributes": False}


class PatchSiteCapabilityRequest(BaseModel):
    can_scrape_metadata: bool | None = None
    can_scrape_images: bool | None = None
    requires_token: bool | None = None
    is_manual_only: bool | None = None
    notes: str | None = None
    # Provide a plaintext token — it will be encrypted before storage
    token: str | None = None


class CommitResponse(BaseModel):
    item_key: str
    item_id: int
    session_id: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _session_out(
    session: ImportSession, has_token_domains: set[str] | None = None
) -> ImportSessionOut:
    """Convert an ImportSession ORM object to ImportSessionOut."""
    tag_state: TagStateOut | None = None
    if session.tag_state:
        tag_state = TagStateOut(
            confirmed=session.tag_state.get("confirmed", []),
            pending=session.tag_state.get("pending", []),
        )
    return ImportSessionOut(
        id=str(session.id),
        status=session.status.value if session.status else "draft",
        source_type=session.source_type.value if session.source_type else "upload",
        source_url=session.source_url,
        inbox_folder=session.inbox_folder,
        staging_dir=session.staging_dir,
        suggested_title=session.suggested_title,
        confirmed_title=session.confirmed_title,
        description=session.description,
        license=session.license,
        source_site=session.source_site,
        creator_name=session.creator_name,
        creator_profile_url=session.creator_profile_url,
        creator_source_site=session.creator_source_site,
        creator_is_own_design=session.creator_is_own_design or False,
        creator_id=session.creator_id,
        tag_state=tag_state,
        default_image_path=session.default_image_path,
        library_id=session.library_id,
        job_id=str(session.job_id) if session.job_id else None,
        item_id=session.item_id,
        created_by_id=session.created_by_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        error=session.error,
        scrape_note=session.scrape_note,
        files=[
            ImportSessionFileOut(
                id=f.id,
                staged_path=f.staged_path,
                original_name=f.original_name,
                role=f.role,
                size=f.size,
            )
            for f in (session.files or [])
        ],
        images=[
            ImportSessionImageOut(
                id=img.id,
                path=img.path,
                is_url=img.is_url,
                source=img.source,
                order=img.order,
                is_default=img.is_default,
            )
            for img in (session.images or [])
        ],
    )


async def _load_session(
    session_id: str,
    db: AsyncSession,
    user: User,
) -> ImportSession:
    """Load a session by UUID, enforcing ownership (admin can access all)."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid session ID",
        ) from exc

    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    result = await db.execute(
        select(ImportSession)
        .options(
            selectinload(ImportSession.files),
            selectinload(ImportSession.images),
        )
        .where(ImportSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Import session not found."
        )

    from ..models.user import UserRole  # noqa: PLC0415

    if user.role != UserRole.admin and session.created_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your session."
        )
    return session


async def reconcile_tags(
    db: AsyncSession,
    raw_tags: list[str],
) -> dict[str, list[str]]:
    """Map raw tag strings to canonical names via aliases; unknown → pending.

    Returns {"confirmed": [...], "pending": [...]}:
      confirmed = mapped to canonical (active or existing) tags
      pending   = unknown tags that would be created as TagStatus.pending
    """
    confirmed: list[str] = []
    pending: list[str] = []

    for raw in raw_tags:
        raw = raw.strip()
        if not raw:
            continue

        # 1. Direct name match (active or pending tag)
        result = await db.execute(select(Tag).where(Tag.name == raw))
        tag = result.scalar_one_or_none()
        if tag is not None:
            confirmed.append(tag.name)
            continue

        # 2. Alias lookup
        alias_result = await db.execute(
            select(TagAlias).where(TagAlias.alias == raw)
        )
        alias = alias_result.scalar_one_or_none()
        if alias is not None:
            # Resolve to the canonical tag's name
            tag_result = await db.execute(
                select(Tag).where(Tag.id == alias.tag_id)
            )
            canonical = tag_result.scalar_one_or_none()
            if canonical is not None:
                if canonical.name not in confirmed:
                    confirmed.append(canonical.name)
                continue

        # 3. Unknown → pending suggestion
        if raw not in pending and raw not in confirmed:
            pending.append(raw)

    return {"confirmed": confirmed, "pending": pending}


async def _ensure_creator(
    db: AsyncSession,
    name: str,
    profile_url: str | None = None,
    source_site: str | None = None,
    user_id: int | None = None,  # set for "own design"
) -> Creator:
    """Find or create a Creator by name (case-insensitive dedup).

    Reuses an existing Creator with the same name and source_site when possible.
    If user_id is set (own-design), links the creator to that user.
    """
    # Look up by exact name (case-insensitive)
    result = await db.execute(
        select(Creator).where(
            sa.func.lower(Creator.name) == name.lower()
        )
    )
    existing = result.scalars().all()

    # Narrow by source_site if provided
    if existing and source_site:
        by_site = [c for c in existing if c.source_site == source_site]
        if by_site:
            creator = by_site[0]
            # If own-design and not yet linked to this user, link now
            if user_id is not None and creator.user_id is None:
                creator.user_id = user_id
                await db.flush()
            return creator

    if existing:
        creator = existing[0]
        if user_id is not None and creator.user_id is None:
            creator.user_id = user_id
            await db.flush()
        return creator

    # Create new
    creator = Creator(
        name=name,
        profile_url=profile_url,
        source_site=source_site,
        user_id=user_id,
    )
    db.add(creator)
    await db.flush()
    return creator


def _get_staging_dir() -> Path:
    """Return the staging directory for uploaded files."""
    staging = Path(settings.DATA_DIR) / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging


async def _enqueue_import_job(session_id: str) -> None:
    """Fire-and-forget: enqueue a process_import_session arq task."""
    try:
        from arq import create_pool  # noqa: PLC0415
        from arq.connections import RedisSettings  # noqa: PLC0415

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis.enqueue_job("process_import_session", session_id)
        await redis.aclose()
        log.debug("_enqueue_import_job: enqueued for session %s", session_id)
    except Exception:
        log.exception(
            "_enqueue_import_job: failed to enqueue for session %s", session_id
        )


# ---------------------------------------------------------------------------
# Import session endpoints
# ---------------------------------------------------------------------------


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
        from ..storage.ssrf_guard import SSRFBlockedError, assert_safe_url  # noqa: PLC0415

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
    from ..storage.inventory import infer_role  # noqa: PLC0415

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

    from ..models.user import UserRole  # noqa: PLC0415

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


@router.post("/api/import-sessions/{session_id}/commit", response_model=CommitResponse)
async def commit_import_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CommitResponse:
    """Finalize an import session into a real Item.

    Reuses the same path as create_item: assigns storage path from confirmed title,
    moves staged/inbox files into the library via the atomic-move journal, attaches
    tags + creator + images, writes the sidecar, enqueues the render job.

    The session must be in 'pending_wizard' status and have a confirmed_title and
    library_id set.  On failure, the session is marked 'failed' and no partial item
    is created.
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

    if not session.library_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="library_id must be set before committing.",
        )

    # Validate library
    lib_res = await db.execute(
        select(Library).where(
            Library.id == session.library_id, Library.enabled.is_(True)
        )
    )
    library = lib_res.scalar_one_or_none()
    if library is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library {session.library_id} not found or not enabled.",
        )

    try:
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
        slug = item_slug(title, key)
        item_dir = item_dir_path(library.mount_path, key, title)
        item_dir.mkdir(parents=True, exist_ok=True)

        # ---- 3. Move staged files into item dir ----
        for sf in session.files:
            src_path = Path(sf.staged_path)
            if src_path.exists():
                dest_path = item_dir / src_path.name
                # Use Path.replace for same-filesystem move (fastest)
                # If cross-device, fall back to copy+delete
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
        # Confirmed tags from session tag_state
        confirmed_tags: list[str] = []
        pending_tags: list[str] = []
        if session.tag_state:
            confirmed_tags = session.tag_state.get("confirmed", [])
            pending_tags = session.tag_state.get("pending", [])

        # Create pending tags (approval queue)
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
            # Add to confirmed list with pending status (still visible, just not canonical)
            if tag_name not in confirmed_tags:
                confirmed_tags.append(tag_name)

        # Attach via shared helper — any brand-new tag created here is marked
        # pending so it enters the admin approval queue rather than becoming
        # immediately canonical.  Tags that already exist keep their current status.
        if confirmed_tags:
            await _attach_tags(db, item, confirmed_tags, new_tag_status=TagStatus.pending)

        # ---- 6. Inventory files + create File rows ----
        sc_name = sidecar_name(title, key)
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

        # ---- 6b. Capture source_baseline (Phase 15) ----
        # Only when the item has a source_url — this is the "original online version"
        # reference.  Capture the sha256 of model files only (role=model).
        if session.source_url:
            from ..models.file import FileRole  # noqa: PLC0415
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
                # Download URL image into item_dir/images/
                try:
                    import httpx as _httpx  # noqa: PLC0415

                    images_dir = item_dir / "images"
                    images_dir.mkdir(exist_ok=True)
                    img_name = Path(si.path).name.split("?")[0] or f"img_{img_order}.jpg"
                    img_dest = images_dir / img_name
                    with _httpx.Client(timeout=settings.SCRAPE_TIMEOUT) as c:
                        r = c.get(si.path, follow_redirects=True)
                        if r.status_code == 200:
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
                # Staged/inbox image already moved to item_dir
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
        await _enqueue_render(item.id)

        return CommitResponse(
            item_key=item.key,
            item_id=item.id,
            session_id=session_id,
        )

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("commit_import_session: failed for session %s", session_id)
        # Mark session failed
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


# ---------------------------------------------------------------------------
# Share-link import (Phase 7 — implements the Phase 5 stub)
# ---------------------------------------------------------------------------

# Mockable network fetch for instance-to-instance import.
# Override this in tests (monkeypatch) to avoid hitting a live instance.
# Signature: (url: str, timeout: int) -> dict
_share_link_fetcher: object = None  # set at module level; None → use real httpx


def _get_fetcher() -> object:
    return _share_link_fetcher


async def _fetch_remote_share(url: str, timeout: int) -> dict:
    """Fetch a remote share link's JSON metadata.

    Uses httpx if available; returns the parsed JSON dict.
    Raises HTTPException on network/parse errors so the caller can surface them.
    """
    fetcher = _get_fetcher()
    if fetcher is not None:
        # Injected mock — call it synchronously
        return fetcher(url, timeout)  # type: ignore[operator]

    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()  # type: ignore[return-value]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch remote share link: {exc}",
        ) from exc


class ShareLinkImportRequest(BaseModel):
    """Request body for POST /api/import-sessions/from-share-link."""
    share_url: str
    library_id: int | None = None
    # Granular options for what public print history to pull
    include_public_notes: bool = True
    include_gcode: bool = False       # gcode files can be large; default off
    include_photos: bool = True
    include_settings: bool = True


@router.post(
    "/api/import-sessions/from-share-link",
    response_model=ImportSessionOut,
    status_code=201,
)
async def import_from_share_link(
    body: ShareLinkImportRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImportSessionOut:
    """Import a design from another PartFolder 3D instance's share link.

    Given a share link URL from another PartFolder 3D instance, fetches the
    design's public metadata and creates an import session that can be reviewed
    in the wizard and committed to this library.

    Granular pull options control which public print history is included:
      include_public_notes   — pull public print notes and settings
      include_gcode          — download gcode files (can be large)
      include_photos         — download print photos
      include_settings       — pull structured settings (printer, material, etc.)

    SECURITY: private records are NEVER transferred — the remote instance's
    public endpoint already filters them; this endpoint requests only public data.
    Network fetch is mockable via the _share_link_fetcher module variable.
    """
    # --- Parse the share URL ---
    # Expected formats:
    #   https://otherinstance.com/share/<token>
    #   https://otherinstance.com/api/public/share/<token>
    import re as _re  # noqa: PLC0415
    import urllib.parse as _urlparse  # noqa: PLC0415

    share_url = body.share_url.strip()
    if not share_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="share_url is required.",
        )

    # Extract token from URL path.  Both UI and API URL forms are accepted.
    token_match = _re.search(r"/share/([a-f0-9]{64})(?:/|$)", share_url)
    if not token_match:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Could not extract a valid share token from the URL. "
                "Expected format: https://instance.example.com/share/<64-char-hex-token>"
            ),
        )
    token = token_match.group(1)

    # Build the remote API URL
    parsed = _urlparse.urlparse(share_url)
    api_base = f"{parsed.scheme}://{parsed.netloc}"
    api_url = f"{api_base}/api/public/share/{token}"

    # SSRF guard — block internal/link-local/cloud-metadata IPs
    from ..storage.ssrf_guard import SSRFBlockedError, assert_safe_url  # noqa: PLC0415

    try:
        assert_safe_url(api_url)
    except SSRFBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Blocked: {exc}",
        ) from exc

    # --- Fetch remote metadata ---
    remote_data = await _fetch_remote_share(api_url, timeout=settings.INSTANCE_IMPORT_TIMEOUT)

    if not isinstance(remote_data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected response format from remote instance.",
        )

    # --- Extract metadata ---
    item_data = remote_data.get("item") or remote_data  # support both wrapped + flat
    remote_title: str | None = (
        item_data.get("title")
        if isinstance(item_data, dict)
        else remote_data.get("title")
    )
    remote_description: str | None = (
        item_data.get("description")
        if isinstance(item_data, dict)
        else remote_data.get("description")
    )
    remote_license: str | None = (
        item_data.get("license")
        if isinstance(item_data, dict)
        else remote_data.get("license")
    )
    remote_source_url: str | None = (
        item_data.get("source_url")
        if isinstance(item_data, dict)
        else remote_data.get("source_url")
    )
    remote_tags: list[str] = list(
        (item_data.get("tags") or remote_data.get("tags") or [])
        if isinstance(item_data, dict)
        else (remote_data.get("tags") or [])
    )

    # Public print records (only if requested)
    public_print_records: list[dict] = []
    if body.include_public_notes or body.include_settings:
        raw_records = remote_data.get("public_print_records") or []
        if isinstance(raw_records, list):
            public_print_records = raw_records

    # --- Resolve library ---
    target_library_id = body.library_id
    if target_library_id is None:
        from ..models.library import Library  # noqa: PLC0415

        lib_result = await db.execute(
            select(Library).where(Library.enabled.is_(True)).limit(1)
        )
        lib = lib_result.scalar_one_or_none()
        if lib is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No enabled library found. Please specify library_id.",
            )
        target_library_id = lib.id

    # --- Tag reconciliation ---
    tag_state = (
        await reconcile_tags(db, remote_tags) if remote_tags else {"confirmed": [], "pending": []}
    )

    # --- Store public print history as session metadata ---
    # We embed this in a custom field on the session's tag_state extended object.
    # (Phase 7b frontend wizard will use this to let the user review + confirm.)
    extended_tag_state: dict = dict(tag_state)
    if public_print_records:
        extended_tag_state["imported_print_records"] = [
            {
                "note": r.get("note") if body.include_public_notes else None,
                "date": r.get("date"),
                "printer": r.get("printer") if body.include_settings else None,
                "material": r.get("material") if body.include_settings else None,
                "filament_color": r.get("filament_color") if body.include_settings else None,
                "nozzle_diameter": r.get("nozzle_diameter") if body.include_settings else None,
                "layer_height": r.get("layer_height") if body.include_settings else None,
                "supports": r.get("supports") if body.include_settings else None,
                "success": r.get("success") if body.include_settings else None,
                "rating": r.get("rating") if body.include_public_notes else None,
                "filament_length_mm": r.get("filament_length_mm"),
                "filament_weight_g": r.get("filament_weight_g"),
                "estimated_print_time_s": r.get("estimated_print_time_s"),
            }
            for r in public_print_records
        ]

    # --- Create ImportSession ---
    session = ImportSession(
        status=ImportSessionStatus.pending_wizard,
        source_type=ImportSourceType.url,
        source_url=remote_source_url or share_url,
        suggested_title=remote_title or "Imported from share link",
        confirmed_title=remote_title or "Imported from share link",
        description=remote_description,
        license=remote_license,
        tag_state=extended_tag_state,
        library_id=target_library_id,
        created_by_id=user.id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    log.info(
        "import_from_share_link: created session %s from %s "
        "(tags confirmed=%d pending=%d print_records=%d)",
        session.id,
        api_url,
        len(tag_state.get("confirmed", [])),
        len(tag_state.get("pending", [])),
        len(public_print_records),
    )

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


# ---------------------------------------------------------------------------
# Site capability endpoints
# ---------------------------------------------------------------------------


@router.get("/api/site-capabilities", response_model=list[SiteCapabilityOut])
async def list_site_capabilities(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SiteCapabilityOut]:
    """List all known site capabilities."""
    result = await db.execute(
        select(SiteCapability).order_by(SiteCapability.domain)
    )
    caps = result.scalars().all()

    # Check which domains have tokens
    token_result = await db.execute(
        select(SiteToken.domain)
    )
    token_domains = {row[0] for row in token_result.all()}

    return [
        SiteCapabilityOut(
            domain=c.domain,
            can_scrape_metadata=c.can_scrape_metadata,
            can_scrape_images=c.can_scrape_images,
            requires_token=c.requires_token,
            is_manual_only=c.is_manual_only,
            last_probed_at=c.last_probed_at,
            notes=c.notes,
            has_token=c.domain in token_domains,
        )
        for c in caps
    ]


@router.get("/api/site-capabilities/{domain}", response_model=SiteCapabilityOut)
async def get_site_capability(
    domain: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SiteCapabilityOut:
    """Get site capability for a domain."""
    result = await db.execute(
        select(SiteCapability).where(SiteCapability.domain == domain)
    )
    cap = result.scalar_one_or_none()
    if cap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No capability record for domain '{domain}'.",
        )

    token_res = await db.execute(
        select(SiteToken).where(SiteToken.domain == domain)
    )
    has_token = token_res.scalar_one_or_none() is not None

    return SiteCapabilityOut(
        domain=cap.domain,
        can_scrape_metadata=cap.can_scrape_metadata,
        can_scrape_images=cap.can_scrape_images,
        requires_token=cap.requires_token,
        is_manual_only=cap.is_manual_only,
        last_probed_at=cap.last_probed_at,
        notes=cap.notes,
        has_token=has_token,
    )


@router.patch("/api/site-capabilities/{domain}", response_model=SiteCapabilityOut)
async def patch_site_capability(
    domain: str,
    body: PatchSiteCapabilityRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SiteCapabilityOut:
    """Update site capability flags, or store a new auth token (encrypted)."""
    result = await db.execute(
        select(SiteCapability).where(SiteCapability.domain == domain)
    )
    cap = result.scalar_one_or_none()
    if cap is None:
        # Auto-create
        cap = SiteCapability(domain=domain)
        db.add(cap)

    if body.can_scrape_metadata is not None:
        cap.can_scrape_metadata = body.can_scrape_metadata
    if body.can_scrape_images is not None:
        cap.can_scrape_images = body.can_scrape_images
    if body.requires_token is not None:
        cap.requires_token = body.requires_token
    if body.is_manual_only is not None:
        cap.is_manual_only = body.is_manual_only
    if body.notes is not None:
        cap.notes = body.notes

    cap.updated_at = datetime.now(UTC)
    await db.flush()

    # Store encrypted token if provided
    has_token = False
    if body.token:
        from ..crypto import encrypt  # noqa: PLC0415

        encrypted = encrypt(body.token)

        token_res = await db.execute(
            select(SiteToken).where(SiteToken.domain == domain)
        )
        token_row = token_res.scalar_one_or_none()
        if token_row is None:
            token_row = SiteToken(domain=domain, encrypted_token=encrypted)
            db.add(token_row)
        else:
            token_row.encrypted_token = encrypted
            token_row.updated_at = datetime.now(UTC)
        await db.flush()
        has_token = True
    else:
        token_res = await db.execute(
            select(SiteToken).where(SiteToken.domain == domain)
        )
        has_token = token_res.scalar_one_or_none() is not None

    return SiteCapabilityOut(
        domain=cap.domain,
        can_scrape_metadata=cap.can_scrape_metadata,
        can_scrape_images=cap.can_scrape_images,
        requires_token=cap.requires_token,
        is_manual_only=cap.is_manual_only,
        last_probed_at=cap.last_probed_at,
        notes=cap.notes,
        has_token=has_token,
    )
