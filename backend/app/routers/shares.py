"""Sharing API — Phase 7 (PRD §10).

Public (UN-authenticated, token-gated):
  GET  /api/public/share/{token}                  → share metadata
  GET  /api/public/share/{token}/files/{path}     → stream file (item_design scope)
  POST /api/public/share/{token}/zip              → queue public ZIP
  GET  /api/public/share/{token}/zip/{bundle_id}  → poll / download public ZIP
  GET  /api/public/share/{token}/catalog          → read-only catalog browse (full_site)

Private (authenticated, owner or admin):
  POST /api/items/{key}/shares                    → mint per-design link
  GET  /api/items/{key}/shares                    → list per-design links for item
  POST /api/admin/shares/site                     → mint full-site link (admin only)
  GET  /api/admin/shares/site                     → list full-site links (admin only)
  POST /api/shares/{share_id}/revoke              → revoke a link
  GET  /api/shares/{share_id}/audit               → view audit events for a link

Security properties (enforced server-side on EVERY public request):
  - Token must exist in the database.
  - Token must not be expired (expires_at null or in the future).
  - Token must not be revoked.
  - Public endpoints NEVER return private print records (visibility != 'public').
  - Public ZIP downloads NEVER include private print history.
  - Expiry + revocation are checked on every request, not just at link creation.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_current_user, get_db, require_admin
from ..config import settings
from ..models.download_bundle import DownloadBundle
from ..models.file import File
from ..models.item import Item
from ..models.print_record import PrintRecord
from ..models.share_audit_event import ShareAuditEvent
from ..models.share_link import ShareLink
from ..models.tag import ItemTag, Tag
from ..models.user import User, UserRole

log = logging.getLogger(__name__)

router = APIRouter(tags=["shares"])

# Default ZIP TTL for public bundles (same as private)
PUBLIC_ZIP_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class ShareLinkOut(BaseModel):
    id: int
    token: str
    scope: str
    item_id: int | None
    item_key: str | None = None
    created_by_id: int | None
    expires_at: datetime | None
    revoked: bool
    revoked_at: datetime | None
    label: str | None
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class MintShareIn(BaseModel):
    label: str | None = None
    # Expiry in days from now; None → use default from settings; 0 → never expires
    expires_days: int | None = None


class MintSiteShareIn(BaseModel):
    label: str | None = None
    expires_days: int | None = None


class ShareAuditEventOut(BaseModel):
    id: int
    share_link_id: int
    event_type: str
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicItemOut(BaseModel):
    """Public view of an item — never includes private data."""
    key: str
    title: str
    description: str | None
    license: str | None
    source_url: str | None
    source_site: str | None
    tags: list[str]
    public_print_records: list[dict]
    # Phase 15: local-modification tracking (baseline hashes NOT exposed publicly)
    is_modified: bool = False


class BundleOut(BaseModel):
    id: str
    status: str
    expires_at: datetime | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from X-Forwarded-For or request.client."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _get_user_agent(request: Request) -> str | None:
    return request.headers.get("User-Agent")


async def _resolve_share_link(
    token: str, db: AsyncSession, request: Request
) -> ShareLink:
    """Load and validate a share link.  Raises 404 or 403 for invalid/expired/revoked."""
    result = await db.execute(
        select(ShareLink).where(ShareLink.token == token)
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found."
        )

    now = datetime.now(UTC)

    # Check expiry
    if link.expires_at is not None and link.expires_at < now:
        # Record expiry event (once per check; idempotent enough for audit)
        _record_audit(db, link.id, "expired", request)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This share link has expired.",
        )

    # Check revocation
    if link.revoked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This share link has been revoked.",
        )

    return link


def _record_audit(
    db: AsyncSession,
    share_link_id: int,
    event_type: str,
    request: Request | None = None,
) -> None:
    """Schedule an audit event insert (fire-and-forget within the same transaction)."""
    ip = _get_client_ip(request) if request else None
    ua = _get_user_agent(request) if request else None
    event = ShareAuditEvent(
        share_link_id=share_link_id,
        event_type=event_type,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(event)


async def _get_item_or_404(key: str, db: AsyncSession) -> Item:
    result = await db.execute(select(Item).where(Item.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return item


def _compute_inventory_hash(files: list[File]) -> str:
    parts = sorted(f"{f.path}:{f.sha256 or ''}:{f.size}" for f in files)
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


async def _compute_expiry(expires_days: int | None, db: AsyncSession) -> datetime | None:
    """Compute expiry datetime from expires_days param + default setting.

    expires_days=None → use share_default_expiry_days setting
    expires_days=0    → never expires (None)
    expires_days>0    → now + N days
    """
    if expires_days == 0:
        return None  # Never expires

    if expires_days is None:
        # Load default from settings table
        from ..models.setting import Setting  # noqa: PLC0415

        result = await db.execute(
            select(Setting).where(Setting.key == "share_default_expiry_days")
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value:
            try:
                expires_days = int(setting.value)
            except ValueError:
                expires_days = 30  # fallback
        else:
            expires_days = 30  # default: 30 days

    if expires_days == 0:
        return None
    return datetime.now(UTC) + timedelta(days=expires_days)


# ---------------------------------------------------------------------------
# Public endpoints (UN-authenticated, token-gated)
# ---------------------------------------------------------------------------


@router.get("/api/public/share/{token}", response_model=PublicItemOut)
async def public_share_view(
    token: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PublicItemOut:
    """Public read-only view of a shared item or catalog.

    SECURITY: only public print records (visibility='public') are returned.
    Private records NEVER appear here.  Expiry and revocation are checked.
    """
    link = await _resolve_share_link(token, db, request)

    if link.scope != "item_design":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link is for full-site browse, not a single item.",
        )

    if link.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link has no associated item.",
        )

    # Load item
    item_result = await db.execute(select(Item).where(Item.id == link.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        )

    # Load public tags
    tags_result = await db.execute(
        sa.select(Tag.name)
        .join(ItemTag, ItemTag.tag_id == Tag.id)
        .where(ItemTag.item_id == item.id)
    )
    tag_names = [row[0] for row in tags_result.all()]

    # Load PUBLIC print records only — NEVER private records
    pr_result = await db.execute(
        select(PrintRecord).where(
            PrintRecord.item_id == item.id,
            PrintRecord.visibility == "public",  # SECURITY: public only
        ).order_by(PrintRecord.created_at.desc())
    )
    public_records = pr_result.scalars().all()

    # Serialize print records — strip any potentially sensitive fields
    serialized_records = [
        {
            "id": r.id,
            "note": r.note,
            "date": r.date.isoformat() if r.date else None,
            "printer": r.printer,
            "material": r.material,
            "filament_color": r.filament_color,
            "nozzle_diameter": r.nozzle_diameter,
            "layer_height": r.layer_height,
            "supports": r.supports,
            "success": r.success,
            "rating": r.rating,
            "filament_length_mm": r.filament_length_mm,
            "filament_weight_g": r.filament_weight_g,
            "estimated_print_time_s": r.estimated_print_time_s,
            # Do NOT expose file paths — they reveal filesystem layout
        }
        for r in public_records
    ]

    # Phase 15: compute effective is_modified (don't expose baseline hashes)
    from ..routers.items import _effective_is_modified  # noqa: PLC0415

    # Record access event
    _record_audit(db, link.id, "accessed_view", request)

    return PublicItemOut(
        key=item.key,
        title=item.title,
        description=item.description,
        license=item.license,
        source_url=item.source_url,
        source_site=item.source_site,
        tags=tag_names,
        public_print_records=serialized_records,
        is_modified=_effective_is_modified(item),
    )


@router.get("/api/public/share/{token}/files/{path:path}")
async def public_share_download_file(
    token: str,
    path: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Download a single file from a shared item.

    SECURITY: path traversal prevented; only files inside the item dir are served.
    """
    link = await _resolve_share_link(token, db, request)

    if link.scope != "item_design" or link.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link does not support file downloads.",
        )

    item_result = await db.execute(select(Item).where(Item.id == link.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    item_dir = Path(item.dir_path).resolve()
    clean_path = path.lstrip("/")
    requested = (item_dir / clean_path).resolve()

    # Path traversal containment barrier: resolved path must remain inside item_dir.
    if not requested.is_relative_to(item_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path (outside item directory).",
        )

    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    # Record download event
    _record_audit(db, link.id, "accessed_download", request)

    return FileResponse(
        path=str(requested),
        filename=requested.name,
        media_type="application/octet-stream",
    )


@router.post("/api/public/share/{token}/zip", response_model=BundleOut)
async def public_share_queue_zip(
    token: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BundleOut:
    """Queue a ZIP download for a public share link.

    SECURITY: bundles created via public links NEVER include private print history.
    requester_user_id=None → worker treats as anonymous → only public records if any.
    """
    link = await _resolve_share_link(token, db, request)

    if link.scope != "item_design" or link.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link does not support ZIP downloads.",
        )

    item_result = await db.execute(select(Item).where(Item.id == link.item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    files_result = await db.execute(select(File).where(File.item_id == item.id))
    files = list(files_result.scalars().all())
    current_hash = _compute_inventory_hash(files)
    now_utc = datetime.now(UTC)

    # Reuse existing public bundle if valid
    existing_result = await db.execute(
        select(DownloadBundle).where(
            DownloadBundle.item_id == item.id,
            DownloadBundle.status.in_(["pending", "ready"]),
            DownloadBundle.expires_at > now_utc,
            DownloadBundle.requester_user_id.is_(None),  # public bundles only
            DownloadBundle.include_print_history.is_(False),
        ).order_by(DownloadBundle.created_at.desc())
    )
    for bundle in existing_result.scalars().all():
        if bundle.status == "pending":
            return BundleOut(id=str(bundle.id), status="pending", expires_at=bundle.expires_at)
        if bundle.status == "ready" and bundle.inventory_hash == current_hash:
            return BundleOut(id=str(bundle.id), status="ready", expires_at=bundle.expires_at)

    expires_at = now_utc + timedelta(hours=PUBLIC_ZIP_TTL_HOURS)
    bundle = DownloadBundle(
        id=uuid.uuid4(),
        item_id=item.id,
        status="pending",
        inventory_hash=current_hash,
        expires_at=expires_at,
        include_print_history=False,  # SECURITY: never include history on public links
        requester_user_id=None,       # SECURITY: anonymous
    )
    db.add(bundle)
    await db.flush()
    await db.refresh(bundle)

    try:
        from arq import create_pool  # noqa: PLC0415
        from arq.connections import RedisSettings  # noqa: PLC0415

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis.enqueue_job("build_zip_bundle", str(bundle.id))
        await redis.aclose()
    except Exception:
        log.exception("Failed to enqueue build_zip_bundle for public bundle %s", bundle.id)

    _record_audit(db, link.id, "accessed_download", request)
    return BundleOut(id=str(bundle.id), status="pending", expires_at=bundle.expires_at)


@router.get("/api/public/share/{token}/zip/{bundle_id}", response_model=BundleOut)
async def public_share_poll_zip(
    token: str,
    bundle_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    download: bool = Query(default=False),
) -> BundleOut | FileResponse:
    """Poll or download a public ZIP bundle."""
    link = await _resolve_share_link(token, db, request)

    if link.scope != "item_design" or link.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link does not support ZIP downloads.",
        )

    try:
        bundle_uuid = uuid.UUID(bundle_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid bundle id."
        ) from exc

    result = await db.execute(
        select(DownloadBundle).where(
            DownloadBundle.id == bundle_uuid,
            DownloadBundle.item_id == link.item_id,
        )
    )
    bundle = result.scalar_one_or_none()
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found.")

    now_utc = datetime.now(UTC)
    if bundle.expires_at <= now_utc and bundle.status != "ready":
        return BundleOut(id=str(bundle.id), status="expired")
    if bundle.status == "failed":
        return BundleOut(id=str(bundle.id), status="failed", error_message=bundle.error_message)
    if bundle.status == "pending":
        return BundleOut(id=str(bundle.id), status="pending", expires_at=bundle.expires_at)

    if not bundle.bundle_path or not Path(bundle.bundle_path).exists():
        bundle.status = "failed"
        bundle.error_message = "ZIP file missing on disk"
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ZIP file is missing on disk.",
        )

    if download:
        item_result = await db.execute(select(Item).where(Item.id == link.item_id))
        item = item_result.scalar_one_or_none()
        filename = f"{item.slug if item else 'download'}.zip"
        _record_audit(db, link.id, "accessed_download", request)
        return FileResponse(
            path=bundle.bundle_path,
            filename=filename,
            media_type="application/zip",
        )

    return BundleOut(id=str(bundle.id), status="ready", expires_at=bundle.expires_at)


@router.get("/api/public/share/{token}/catalog")
async def public_share_catalog(
    token: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Read-only catalog browse for full_site share links.

    Returns a paginated list of items (title, key, description, tags).
    SECURITY: private data is never included.
    """
    link = await _resolve_share_link(token, db, request)

    if link.scope != "full_site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link is for a single item, not a catalog browse.",
        )

    # Paginated item list
    offset = (page - 1) * per_page
    items_result = await db.execute(
        select(Item.id, Item.key, Item.title, Item.description)
        .order_by(Item.title)
        .offset(offset)
        .limit(per_page)
    )
    rows = items_result.all()

    count_result = await db.execute(sa.select(sa.func.count(Item.id)))
    total: int = count_result.scalar_one() or 0

    _record_audit(db, link.id, "accessed_view", request)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {"key": r[1], "title": r[2], "description": r[3]}
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Private: mint / list / revoke share links
# ---------------------------------------------------------------------------


@router.post("/api/items/{key}/shares", response_model=ShareLinkOut, status_code=201)
async def mint_item_share(
    key: str,
    body: MintShareIn,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShareLinkOut:
    """Mint a per-design share link for an item."""
    item = await _get_item_or_404(key, db)
    expires_at = await _compute_expiry(body.expires_days, db)

    link = ShareLink(
        scope="item_design",
        item_id=item.id,
        created_by_id=user.id,
        expires_at=expires_at,
        label=body.label,
    )
    db.add(link)
    await db.flush()
    await db.refresh(link)

    # Record "created" audit event
    _record_audit(db, link.id, "created")
    await db.flush()

    return _link_to_out(link, item)


@router.get("/api/items/{key}/shares", response_model=list[ShareLinkOut])
async def list_item_shares(
    key: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ShareLinkOut]:
    """List all share links for an item."""
    item = await _get_item_or_404(key, db)

    result = await db.execute(
        select(ShareLink).where(
            ShareLink.item_id == item.id,
            ShareLink.scope == "item_design",
        ).order_by(ShareLink.created_at.desc())
    )
    links = result.scalars().all()
    return [_link_to_out(link, item) for link in links]


@router.post("/api/admin/shares/site", response_model=ShareLinkOut, status_code=201)
async def mint_site_share(
    body: MintSiteShareIn,
    user: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShareLinkOut:
    """Mint a full-site share link (admin only)."""
    expires_at = await _compute_expiry(body.expires_days, db)

    link = ShareLink(
        scope="full_site",
        item_id=None,
        created_by_id=user.id,
        expires_at=expires_at,
        label=body.label,
    )
    db.add(link)
    await db.flush()
    await db.refresh(link)

    _record_audit(db, link.id, "created")
    await db.flush()

    return _link_to_out(link, None)


@router.get("/api/admin/shares/site", response_model=list[ShareLinkOut])
async def list_site_shares(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ShareLinkOut]:
    """List all full-site share links (admin only)."""
    result = await db.execute(
        select(ShareLink).where(ShareLink.scope == "full_site")
        .order_by(ShareLink.created_at.desc())
    )
    links = result.scalars().all()
    return [_link_to_out(link, None) for link in links]


@router.post("/api/shares/{share_id}/revoke", response_model=ShareLinkOut)
async def revoke_share(
    share_id: int,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShareLinkOut:
    """Revoke a share link.

    Admins can revoke any link.  Non-admins can only revoke links they created.
    """
    result = await db.execute(select(ShareLink).where(ShareLink.id == share_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found.")

    if user.role != UserRole.admin and link.created_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to revoke this link.",
        )

    if link.revoked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Share link is already revoked.",
        )

    link.revoked = True
    link.revoked_at = datetime.now(UTC)
    link.revoked_by_id = user.id

    _record_audit(db, link.id, "revoked")
    await db.flush()
    await db.refresh(link)

    # Load item if item_design scope
    item = None
    if link.item_id is not None:
        ir = await db.execute(select(Item).where(Item.id == link.item_id))
        item = ir.scalar_one_or_none()

    return _link_to_out(link, item)


@router.get("/api/shares/{share_id}/audit", response_model=list[ShareAuditEventOut])
async def get_share_audit(
    share_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ShareAuditEventOut]:
    """View audit events for a share link.

    Admins see all links' audit events.  Non-admins see only their own links.
    """
    result = await db.execute(select(ShareLink).where(ShareLink.id == share_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found.")

    if user.role != UserRole.admin and link.created_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this link's audit log.",
        )

    events_result = await db.execute(
        select(ShareAuditEvent)
        .where(ShareAuditEvent.share_link_id == share_id)
        .order_by(ShareAuditEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        ShareAuditEventOut(
            id=e.id,
            share_link_id=e.share_link_id,
            event_type=e.event_type,
            ip_address=e.ip_address,
            user_agent=e.user_agent,
            created_at=e.created_at,
        )
        for e in events_result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _link_to_out(link: ShareLink, item: Item | None) -> ShareLinkOut:
    return ShareLinkOut(
        id=link.id,
        token=link.token,
        scope=link.scope,
        item_id=link.item_id,
        item_key=item.key if item else None,
        created_by_id=link.created_by_id,
        expires_at=link.expires_at,
        revoked=link.revoked,
        revoked_at=link.revoked_at,
        label=link.label,
        created_at=link.created_at,
        is_active=link.is_active(),
    )
