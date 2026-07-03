"""Import sessions router package.

Re-exports the combined router and reconcile_tags for backward compatibility.
Tests mock _share_link_fetcher at the module level of this package.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import csrf_protect, get_current_user, get_db
from ...config import settings
from ...models.import_session import ImportSession, ImportSessionStatus, ImportSourceType
from ...models.user import User
from ...storage.link_url import normalize_link_url
from .helpers import (  # noqa: F401 (reconcile_tags is imported by tests and worker tasks)
    _session_out,
    reconcile_tags,
)
from .schemas import ImportSessionOut
from .sessions import router as _sessions_router
from .site_caps import router as _site_caps_router

log = logging.getLogger(__name__)

# Module-level variable: tests set this to a mock callable; None → use real httpx
_share_link_fetcher: object = None


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
            # follow_redirects=False is explicit: the SSRF guard validates the
            # exact URL being fetched; if we followed redirects the guard would
            # not cover the final destination, opening an SSRF bypass.
            resp = await client.get(url, follow_redirects=False)
            resp.raise_for_status()
            return resp.json()  # type: ignore[return-value]
    except Exception as exc:
        log.warning("_fetch_remote_share: failed to fetch remote share link: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch remote share link.",
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


# ---------------------------------------------------------------------------
# Combined router
# ---------------------------------------------------------------------------

router = APIRouter()
router.include_router(_sessions_router)
router.include_router(_site_caps_router)


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
    import re as _re  # noqa: PLC0415
    import urllib.parse as _urlparse  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415
    from sqlalchemy.orm import selectinload  # noqa: PLC0415

    from ...models.library import Library  # noqa: PLC0415

    share_url = body.share_url.strip()
    if not share_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="share_url is required.",
        )

    # Extract token from URL path
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
    from ...storage.ssrf_guard import SSRFBlockedError, assert_safe_url  # noqa: PLC0415

    try:
        assert_safe_url(api_url)
    except SSRFBlockedError as exc:
        # Log the specific block reason server-side; return a generic message
        # so we don't leak internal-network topology to the importing user.
        log.warning("import_from_share_link: SSRF-blocked share URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URL is not allowed.",
        ) from exc

    # Fetch remote metadata
    remote_data = await _fetch_remote_share(api_url, timeout=settings.INSTANCE_IMPORT_TIMEOUT)

    if not isinstance(remote_data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected response format from remote instance.",
        )

    # Extract metadata
    item_data = remote_data.get("item") or remote_data
    remote_title: str | None = (
        item_data.get("title") if isinstance(item_data, dict) else remote_data.get("title")
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
    # Drop non-http(s) schemes from the remote instance's source_url so it can't
    # plant a javascript: href on the item / public share page (storage.link_url).
    remote_source_url: str | None = normalize_link_url(
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

    # Resolve library
    target_library_id = body.library_id
    if target_library_id is None:
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

    # Tag reconciliation
    tag_state = (
        await reconcile_tags(db, remote_tags)
        if remote_tags
        else {"confirmed": [], "pending": []}
    )

    # Store public print history as session metadata
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

    # Create ImportSession
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

    # Sanitize api_url for logging: strip CR/LF to prevent log injection.
    _log_url = api_url.replace("\r", "\\r").replace("\n", "\\n")
    log.info(
        "import_from_share_link: created session %s from %s "
        "(tags confirmed=%d pending=%d print_records=%d)",
        session.id,
        _log_url,
        len(tag_state.get("confirmed", [])),
        len(tag_state.get("pending", [])),
        len(public_print_records),
    )

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
