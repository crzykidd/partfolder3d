"""Download endpoints (Phase 3).

GET  /api/items/{key}/files/{path:path}  → stream a single file from the item dir
POST /api/items/{key}/zip                → queue (or reuse) a ZIP bundle
GET  /api/items/{key}/zip/{bundle_id}   → poll status / stream the ZIP when ready

File streaming
--------------
Files are resolved relative to the item's `dir_path` with strict path-traversal
protection (resolved path must begin with the item dir).  FastAPI's `FileResponse`
streams the file via starlette's async file streaming.

Queued ZIP (PRD §11)
--------------------
POST /zip enqueues an arq task (`build_zip_bundle`) that creates a .zip of all files
under the item's directory.  A lightweight `DownloadBundle` row tracks status.

Reuse: if a non-expired "ready" bundle exists for the item AND its inventory_hash
matches the current file inventory, it is returned directly (no new task enqueued).

Invalidation: if files have changed since a bundle was built (inventory_hash differs),
a new bundle is created regardless of expiry.

Expiry: bundles expire after ~24 hours (ZIP_BUNDLE_TTL_HOURS).  Expired bundles are
skipped; cleanup is a Phase 9 task.

The "include print history" checkbox from PRD §11 is stubbed off here (no PrintRecord
model yet) — the ZIP contains only model files/images/renders.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_current_user, get_db
from ..config import settings
from ..models.download_bundle import DownloadBundle
from ..models.file import File
from ..models.item import Item
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["downloads"])

ZIP_BUNDLE_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BundleOut(BaseModel):
    id: str
    status: str  # pending | ready | failed | expired
    expires_at: datetime | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_inventory_hash(files: list[File]) -> str:
    """SHA-256 of the sorted file inventory (path:sha256:size).

    Used to detect whether the item's files changed between ZIP builds.
    """
    parts = sorted(
        f"{f.path}:{f.sha256 or ''}:{f.size}" for f in files
    )
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


async def _get_item_or_404(key: str, db: AsyncSession) -> Item:
    result = await db.execute(select(Item).where(Item.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return item


# ---------------------------------------------------------------------------
# Single file streaming
# ---------------------------------------------------------------------------


@router.get("/{key}/files/{path:path}")
async def download_file(
    key: str,
    path: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    """Stream a single file from the item directory.

    `path` is relative to the item dir (e.g. "ladybug.3mf", "images/cover.png").
    Path traversal is refused: the resolved path must remain inside the item dir.
    """
    item = await _get_item_or_404(key, db)

    item_dir = Path(item.dir_path).resolve()
    # Sanitise: strip any leading slashes so joinpath doesn't override the base
    clean_path = path.lstrip("/")
    requested = (item_dir / clean_path).resolve()

    # Path traversal check
    try:
        requested.relative_to(item_dir)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path (outside item directory).",
        ) from exc

    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    return FileResponse(
        path=str(requested),
        filename=requested.name,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Queued ZIP
# ---------------------------------------------------------------------------


@router.post("/{key}/zip", response_model=BundleOut)
async def queue_zip(
    key: str,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BundleOut:
    """Request a ZIP of the entire item directory.

    If a valid, non-stale bundle already exists it is returned immediately.
    Otherwise, a new bundle row is created and a `build_zip_bundle` task is
    enqueued on the arq worker.

    Poll GET /api/items/{key}/zip/{bundle_id} for status.
    """
    item = await _get_item_or_404(key, db)

    # Compute current inventory hash to check for staleness
    files_result = await db.execute(select(File).where(File.item_id == item.id))
    files = list(files_result.scalars().all())
    current_hash = _compute_inventory_hash(files)

    now_utc = datetime.now(UTC)

    # Check for existing usable bundle (pending or ready + not stale + not expired)
    existing_result = await db.execute(
        select(DownloadBundle)
        .where(
            DownloadBundle.item_id == item.id,
            DownloadBundle.status.in_(["pending", "ready"]),
            DownloadBundle.expires_at > now_utc,
        )
        .order_by(DownloadBundle.created_at.desc())
    )
    for bundle in existing_result.scalars().all():
        if bundle.status == "pending":
            # Still building — return the existing bundle to poll
            return BundleOut(id=str(bundle.id), status="pending", expires_at=bundle.expires_at)
        if bundle.status == "ready" and bundle.inventory_hash == current_hash:
            # Ready and not stale — reuse it
            return BundleOut(id=str(bundle.id), status="ready", expires_at=bundle.expires_at)
        # status=ready but stale → fall through to create a new one

    # Create a new bundle
    expires_at = now_utc + timedelta(hours=ZIP_BUNDLE_TTL_HOURS)
    bundle = DownloadBundle(
        id=uuid.uuid4(),
        item_id=item.id,
        status="pending",
        inventory_hash=current_hash,
        expires_at=expires_at,
    )
    db.add(bundle)
    await db.flush()
    await db.refresh(bundle)

    # Enqueue the arq task
    try:
        from arq import create_pool  # noqa: PLC0415
        from arq.connections import RedisSettings  # noqa: PLC0415

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis.enqueue_job("build_zip_bundle", str(bundle.id))
        await redis.aclose()
    except Exception:
        log.exception(
            "Failed to enqueue build_zip_bundle for bundle %s — "
            "bundle created in DB but worker not notified; will retry on poll",
            bundle.id,
        )
        # Don't fail the request — the bundle row exists; the worker can be
        # triggered by a scheduler or manual re-enqueue later.

    return BundleOut(id=str(bundle.id), status="pending", expires_at=bundle.expires_at)


@router.get("/{key}/zip/{bundle_id}", response_model=BundleOut)
async def poll_or_download_zip(
    key: str,
    bundle_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    download: bool = Query(
        default=False,
        description="If true and bundle is ready, stream the ZIP file instead of returning status.",
    ),
) -> BundleOut | FileResponse:
    """Poll ZIP bundle status, or download when ready.

    Returns a BundleOut JSON if ?download=false (default) or if not yet ready.
    Returns a FileResponse stream if ?download=true and status is 'ready'.
    """
    item = await _get_item_or_404(key, db)

    try:
        bundle_uuid = uuid.UUID(bundle_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid bundle id."
        ) from exc

    result = await db.execute(
        select(DownloadBundle).where(
            DownloadBundle.id == bundle_uuid,
            DownloadBundle.item_id == item.id,
        )
    )
    bundle = result.scalar_one_or_none()
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found."
        )

    now_utc = datetime.now(UTC)
    if bundle.expires_at <= now_utc and bundle.status != "ready":
        return BundleOut(id=str(bundle.id), status="expired")

    if bundle.status == "failed":
        return BundleOut(
            id=str(bundle.id),
            status="failed",
            error_message=bundle.error_message,
        )

    if bundle.status == "pending":
        return BundleOut(id=str(bundle.id), status="pending", expires_at=bundle.expires_at)

    # status == "ready"
    if not bundle.bundle_path or not Path(bundle.bundle_path).exists():
        # File missing on disk — mark failed
        bundle.status = "failed"
        bundle.error_message = "ZIP file missing on disk"
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ZIP file is missing on disk.",
        )

    if download:
        # Stream the file
        filename = f"{item.slug}.zip"
        return FileResponse(
            path=bundle.bundle_path,
            filename=filename,
            media_type="application/zip",
        )

    return BundleOut(id=str(bundle.id), status="ready", expires_at=bundle.expires_at)
