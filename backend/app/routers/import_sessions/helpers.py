"""Import session internal helpers."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

import sqlalchemy as sa
from arq.connections import ArqRedis
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...models.creator import Creator
from ...models.import_session import ImportSession
from ...models.tag import Tag, TagAlias
from ...models.user import User
from .schemas import ImportSessionFileOut, ImportSessionImageOut, ImportSessionOut, TagStateOut

log = logging.getLogger(__name__)


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
                selected=f.selected,
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

    from ...models.user import UserRole  # noqa: PLC0415

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


async def _enqueue_import_job(session_id: str, pool: ArqRedis) -> None:
    """Fire-and-forget: enqueue a process_import_session arq task."""
    try:
        await pool.enqueue_job("process_import_session", session_id)
        log.debug("_enqueue_import_job: enqueued for session %s", session_id)
    except Exception:
        log.exception(
            "_enqueue_import_job: failed to enqueue for session %s", session_id
        )


async def url_matches_enabled_manyfold(db: AsyncSession, url: str | None) -> bool:
    """True if *url*'s domain matches an enabled Manyfold instance.

    Admin-configured Manyfold instances are trusted sources (a self-hosted one
    may resolve to a private/LAN IP), so their URLs are exempt from the
    creation-time SSRF pre-check — mirroring the worker's Manyfold branch and the
    download SSRF exemption. Uses the SAME ``extract_domain`` + enabled-instance
    match as the worker so the entry point and the worker never disagree.
    """
    if not url:
        return False
    from ...models.manyfold import ManyfoldInstance  # noqa: PLC0415
    from ...storage.scraper import extract_domain  # noqa: PLC0415

    domain = extract_domain(url)
    if not domain:
        return False
    res = await db.execute(
        select(ManyfoldInstance).where(
            ManyfoldInstance.domain == domain,
            ManyfoldInstance.enabled.is_(True),
        )
    )
    return res.scalar_one_or_none() is not None
