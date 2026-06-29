"""AI action endpoints for import sessions — Phase 8.

These endpoints are **opt-in and additive**. They augment the manual import
wizard with AI-assisted suggestions. The following contracts apply to every
endpoint here:

* If no AI provider is configured → returns HTTP 200 with ``provider_available=False``
  and empty/null result fields. Never an error.
* If the AI call fails (network, timeout, bad output) → returns HTTP 200 with
  ``provider_available=True`` and an ``error`` field. Never an HTTP 5xx.
* Results are SUGGESTIONS only — the user must explicitly accept via
  PATCH /api/import-sessions/{id}. Nothing is auto-applied.
* These endpoints NEVER block item creation, import commit, or crash the worker.

Usage recording (Phase 13)
--------------------------
* A row is written to ``ai_usage`` after each successful AI call.
* Recording failures are **swallowed** (logged, never re-raised) — usage tracking
  can NEVER break an AI feature or the best-effort AI contract.

Endpoints
---------
POST /api/import-sessions/{id}/ai/suggest-tags
POST /api/import-sessions/{id}/ai/cleanup-description
POST /api/import-sessions/{id}/ai/summarize
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.deps import csrf_protect, get_current_user, get_db
from ..models.import_session import ImportSession
from ..models.tag import Tag, TagStatus
from ..models.user import User, UserRole

log = logging.getLogger(__name__)

router = APIRouter(tags=["ai"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AiStatusOut(BaseModel):
    """Response for GET /api/ai/status — cheap provider-availability check."""

    provider_available: bool


class AiTagSuggestionOut(BaseModel):
    """Response for the AI tag suggestion endpoint."""

    canonical: list[str] = []
    """Existing active tags that match the item content."""

    new_suggestions: list[str] = []
    """Genuinely new tags (≤ 5). Go to the pending approval queue when accepted."""

    provider_available: bool = False
    """False when no provider is enabled — not an error, just no AI configured."""

    error: str | None = None
    """Non-None when the AI call failed; the caller can surface this to the user."""


class AiTextOut(BaseModel):
    """Response for description-cleanup and scrape-summarize endpoints."""

    text: str | None = None
    """The AI-generated text draft. None when no result (no provider or error)."""

    provider_available: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Usage recording helper
# ---------------------------------------------------------------------------


async def _record_usage(
    db: AsyncSession,
    *,
    provider_str: str,
    model_str: str | None,
    action: str,
    input_tokens: int,
    output_tokens: int,
    user_id: int | None,
    success: bool,
) -> None:
    """Write an AiUsage row.  All errors are swallowed — never raises."""
    try:
        from ..models.ai_usage import AiUsage  # noqa: PLC0415

        row = AiUsage(
            provider=provider_str,
            model=model_str,
            action=action,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            user_id=user_id,
            success=success,
        )
        db.add(row)
        await db.flush()
    except Exception:
        log.exception(
            "Failed to record AI usage (provider=%s, action=%s) — swallowed",
            provider_str,
            action,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_session_owned(
    session_id: str,
    db: AsyncSession,
    user: User,
) -> ImportSession:
    """Load an ImportSession by UUID, enforcing ownership (admin sees all)."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid session ID",
        ) from exc

    result = await db.execute(
        select(ImportSession)
        .options(selectinload(ImportSession.files))
        .where(ImportSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import session not found.",
        )
    if user.role != UserRole.admin and session.created_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your session.",
        )
    return session


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/ai/status", response_model=AiStatusOut)
async def ai_status(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiStatusOut:
    """Return whether an enabled AI provider is configured.

    Available to any authenticated user (importers need this to gate the
    wizard AI buttons).  Makes **no** AI or network call and records **no**
    ai_usage row — it only checks for the existence of an enabled provider row.
    """
    from ..ai.client import get_enabled_provider  # noqa: PLC0415

    provider = await get_enabled_provider(db)
    return AiStatusOut(provider_available=provider is not None)


@router.post(
    "/api/import-sessions/{session_id}/ai/suggest-tags",
    response_model=AiTagSuggestionOut,
)
async def ai_suggest_tags(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiTagSuggestionOut:
    """Suggest tags for an import session using the configured AI provider.

    Compares item metadata against all existing active tags (canonical-first)
    and returns:
    - ``canonical``: existing active tags that match the content.
    - ``new_suggestions``: genuinely new tags (≤ 5) not already in the catalog.

    New suggestions are not applied automatically — the user accepts them via
    PATCH /api/import-sessions/{id} confirmed_tags, which feeds the normal
    reconciliation flow (new tags land in the pending approval queue).

    Returns ``provider_available=False`` (no error) when no provider is enabled.
    Returns ``error`` (non-None) when the AI call fails — never a 5xx.
    """
    from ..ai.client import get_enabled_provider, suggest_tags  # noqa: PLC0415

    provider = await get_enabled_provider(db)
    if provider is None:
        return AiTagSuggestionOut(provider_available=False)

    session = await _load_session_owned(session_id, db, user)

    title = session.confirmed_title or session.suggested_title or ""
    description = session.description
    filenames = [f.original_name for f in (session.files or [])]

    # Load all active tags as the canonical reference set.
    tags_result = await db.execute(
        select(Tag.name).where(Tag.status == TagStatus.active)
    )
    existing_tags = [row[0] for row in tags_result.all()]

    ai_result = suggest_tags(
        provider=provider,
        title=title,
        description=description,
        scraped_text=None,  # scraper fills description during processing
        filenames=filenames,
        existing_tags=existing_tags,
    )

    # Record usage — swallowed on failure (belt-and-suspenders outer guard).
    try:
        await _record_usage(
            db,
            provider_str=provider.provider.value,
            model_str=provider.model,
            action="suggest_tags",
            input_tokens=ai_result.input_tokens,
            output_tokens=ai_result.output_tokens,
            user_id=user.id,
            success=ai_result.error is None,
        )
    except Exception:
        log.exception("Usage recording raised outside _record_usage — swallowed")

    return AiTagSuggestionOut(
        canonical=ai_result.canonical,
        new_suggestions=ai_result.new_suggestions,
        provider_available=True,
        error=ai_result.error,
    )


@router.post(
    "/api/import-sessions/{session_id}/ai/cleanup-description",
    response_model=AiTextOut,
)
async def ai_cleanup_description(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiTextOut:
    """Return an AI-cleaned version of the session's description.

    The result is a **suggestion** only — the user must explicitly accept it
    via PATCH /api/import-sessions/{id} (setting description to the returned text).
    Nothing is auto-applied.
    """
    from ..ai.client import cleanup_description, get_enabled_provider  # noqa: PLC0415

    provider = await get_enabled_provider(db)
    if provider is None:
        return AiTextOut(provider_available=False)

    session = await _load_session_owned(session_id, db, user)
    description = session.description or ""
    title = session.confirmed_title or session.suggested_title or ""

    if not description.strip():
        return AiTextOut(
            provider_available=True,
            error="Session has no description to clean up",
        )

    ai_result = cleanup_description(
        provider=provider,
        description=description,
        title=title,
    )

    # Record usage — swallowed on failure (belt-and-suspenders outer guard).
    try:
        await _record_usage(
            db,
            provider_str=provider.provider.value,
            model_str=provider.model,
            action="cleanup_description",
            input_tokens=ai_result.input_tokens,
            output_tokens=ai_result.output_tokens,
            user_id=user.id,
            success=ai_result.error is None,
        )
    except Exception:
        log.exception("Usage recording raised outside _record_usage — swallowed")

    return AiTextOut(
        text=ai_result.text,
        provider_available=True,
        error=ai_result.error,
    )


@router.post(
    "/api/import-sessions/{session_id}/ai/summarize",
    response_model=AiTextOut,
)
async def ai_summarize_scrape(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiTextOut:
    """Summarize the session's scraped content into a description draft.

    Uses the session's current description (populated by the scraper worker)
    as the source text. Returns a short draft — never auto-applied. The user
    must accept via PATCH /api/import-sessions/{id}.
    """
    from ..ai.client import get_enabled_provider, summarize_scrape  # noqa: PLC0415

    provider = await get_enabled_provider(db)
    if provider is None:
        return AiTextOut(provider_available=False)

    session = await _load_session_owned(session_id, db, user)
    title = session.confirmed_title or session.suggested_title or ""

    # Use description as the scraped content source (filled by the import worker).
    scraped_text = session.description or ""
    if not scraped_text.strip() and session.source_url:
        scraped_text = f"Source URL: {session.source_url}"

    if not scraped_text.strip():
        return AiTextOut(
            provider_available=True,
            error="No scraped content available to summarize",
        )

    ai_result = summarize_scrape(
        provider=provider,
        scraped_text=scraped_text,
        title=title,
    )

    # Record usage — swallowed on failure (belt-and-suspenders outer guard).
    try:
        await _record_usage(
            db,
            provider_str=provider.provider.value,
            model_str=provider.model,
            action="summarize",
            input_tokens=ai_result.input_tokens,
            output_tokens=ai_result.output_tokens,
            user_id=user.id,
            success=ai_result.error is None,
        )
    except Exception:
        log.exception("Usage recording raised outside _record_usage — swallowed")

    return AiTextOut(
        text=ai_result.text,
        provider_available=True,
        error=ai_result.error,
    )
