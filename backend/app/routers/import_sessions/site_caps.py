"""Site capability CRUD endpoints."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import csrf_protect, get_current_user, get_db
from ...models.site_capability import SiteCapability, SiteToken
from ...models.user import User
from .schemas import PatchSiteCapabilityRequest, SiteCapabilityOut

log = logging.getLogger(__name__)

router = APIRouter(tags=["import"])


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
        from ...crypto import encrypt  # noqa: PLC0415

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
