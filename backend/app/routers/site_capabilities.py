"""Site-capabilities admin endpoints (Phase 9 — PRD §13).

Admin CRUD over SiteCapability records.  The Phase 5 model + token-encryption
already exist; this router adds the admin API surface.

GET    /api/admin/site-capabilities               → list all capability records
GET    /api/admin/site-capabilities/{domain}      → get one record
PATCH  /api/admin/site-capabilities/{domain}      → update flags (manual-only, notes, etc.)
DELETE /api/admin/site-capabilities/{domain}      → remove a capability record
POST   /api/admin/site-capabilities/{domain}/token → set/update the encrypted token
DELETE /api/admin/site-capabilities/{domain}/token → clear the token
POST   /api/admin/site-capabilities/{domain}/reprobe → reset probed-at to force re-probe
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..crypto import encrypt
from ..models.site_capability import SiteCapability, SiteToken
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/site-capabilities", tags=["admin-site-capabilities"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SiteCapabilityOut(BaseModel):
    domain: str
    can_scrape_metadata: bool
    can_scrape_images: bool
    requires_token: bool
    is_manual_only: bool
    last_probed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    has_token: bool  # whether a SiteToken row exists (never return the plaintext)

    model_config = {"from_attributes": True}


class SiteCapabilityUpdate(BaseModel):
    can_scrape_metadata: bool | None = None
    can_scrape_images: bool | None = None
    requires_token: bool | None = None
    is_manual_only: bool | None = None
    notes: str | None = None


class SetTokenRequest(BaseModel):
    token: str  # plaintext; stored encrypted


class ReprobeResponse(BaseModel):
    domain: str
    last_probed_at: datetime | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_cap_or_404(db: AsyncSession, domain: str) -> SiteCapability:
    result = await db.execute(
        select(SiteCapability).where(SiteCapability.domain == domain)
    )
    cap = result.scalar_one_or_none()
    if cap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No capability record for domain {domain!r}.",
        )
    return cap


async def _has_token(db: AsyncSession, domain: str) -> bool:
    result = await db.execute(
        select(SiteToken.id).where(SiteToken.domain == domain)
    )
    return result.scalar_one_or_none() is not None


async def _cap_out(db: AsyncSession, cap: SiteCapability) -> SiteCapabilityOut:
    # Refresh to pick up server-side defaults (e.g. updated_at after flush).
    await db.refresh(cap)
    return SiteCapabilityOut(
        domain=cap.domain,
        can_scrape_metadata=cap.can_scrape_metadata,
        can_scrape_images=cap.can_scrape_images,
        requires_token=cap.requires_token,
        is_manual_only=cap.is_manual_only,
        last_probed_at=cap.last_probed_at,
        notes=cap.notes,
        created_at=cap.created_at,
        updated_at=cap.updated_at,
        has_token=await _has_token(db, cap.domain),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[SiteCapabilityOut],
    summary="List all site capability records",
)
async def list_site_capabilities(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SiteCapabilityOut]:
    """Return all site capability records ordered by domain."""
    result = await db.execute(
        select(SiteCapability).order_by(SiteCapability.domain)
    )
    caps = list(result.scalars().all())
    return [await _cap_out(db, c) for c in caps]


@router.get(
    "/{domain}",
    response_model=SiteCapabilityOut,
    summary="Get site capability for a domain",
)
async def get_site_capability(
    domain: str,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SiteCapabilityOut:
    cap = await _get_cap_or_404(db, domain)
    return await _cap_out(db, cap)


@router.patch(
    "/{domain}",
    response_model=SiteCapabilityOut,
    summary="Update site capability flags",
)
async def update_site_capability(
    domain: str,
    body: SiteCapabilityUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SiteCapabilityOut:
    """Update flags for a site capability.  Only provided fields are changed."""
    cap = await _get_cap_or_404(db, domain)
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
    await db.flush()
    return await _cap_out(db, cap)


@router.delete(
    "/{domain}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a site capability record",
)
async def delete_site_capability(
    domain: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove a site capability record (and its token, if any).

    The next import session for this domain will re-probe and re-create the record.
    """
    cap = await _get_cap_or_404(db, domain)
    # Remove associated token if present
    token_result = await db.execute(
        select(SiteToken).where(SiteToken.domain == domain)
    )
    token = token_result.scalar_one_or_none()
    if token:
        await db.delete(token)
    await db.delete(cap)
    await db.flush()


@router.post(
    "/{domain}/token",
    response_model=SiteCapabilityOut,
    summary="Set or update the auth token for a domain",
)
async def set_site_token(
    domain: str,
    body: SetTokenRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SiteCapabilityOut:
    """Store an auth token (Fernet-encrypted) for the given domain.

    The plaintext token is encrypted with the instance key and never stored
    in cleartext.  The raw token is accepted here over HTTPS (admin-only).
    """
    cap = await _get_cap_or_404(db, domain)
    encrypted = encrypt(body.token)

    token_result = await db.execute(
        select(SiteToken).where(SiteToken.domain == domain)
    )
    token = token_result.scalar_one_or_none()
    if token:
        token.encrypted_token = encrypted
    else:
        db.add(SiteToken(domain=domain, encrypted_token=encrypted))
        cap.requires_token = True
    await db.flush()
    return await _cap_out(db, cap)


@router.delete(
    "/{domain}/token",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Clear the auth token for a domain",
)
async def clear_site_token(
    domain: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete the stored auth token for a domain."""
    await _get_cap_or_404(db, domain)
    token_result = await db.execute(
        select(SiteToken).where(SiteToken.domain == domain)
    )
    token = token_result.scalar_one_or_none()
    if token:
        await db.delete(token)
        await db.flush()


@router.post(
    "/{domain}/reprobe",
    response_model=ReprobeResponse,
    summary="Reset probe timestamp to trigger re-probe",
)
async def reprobe_site(
    domain: str,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReprobeResponse:
    """Clear last_probed_at so the next import session re-probes this domain."""
    cap = await _get_cap_or_404(db, domain)
    cap.last_probed_at = None
    await db.flush()
    return ReprobeResponse(domain=domain, last_probed_at=None)
