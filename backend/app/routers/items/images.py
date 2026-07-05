"""Item image management: upload and delete.

POST   /api/items/{key}/images              → upload an image (uploaded | captured)
DELETE /api/items/{key}/images/{image_id}   → delete an image

Split out of the former monolithic ``routers/items.py`` (audit §D); routes,
paths, methods, and response models are unchanged.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import sqlalchemy as sa
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi import (
    File as FastAPIFile,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...auth.deps import csrf_protect, get_current_user, get_db
from ...models.image import Image, ImageSource
from ...models.item import Item
from ...models.user import User
from ...services.item_helpers import _write_item_sidecar
from .schemas import ImageOut

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["items"])


# ---------------------------------------------------------------------------
# Allowed image MIME types / extensions for upload
# ---------------------------------------------------------------------------

_ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@router.post("/{key}/images", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    key: str,
    file: Annotated[UploadFile, FastAPIFile(...)],
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source: Annotated[str, Query()] = "uploaded",
) -> ImageOut:
    """Upload an image to an existing item.

    Accepts png/jpg/jpeg/webp/gif.  Writes the file into the item's
    ``images/`` subdirectory with a safe unique name and creates an Image row.
    ``source`` query param accepts ``uploaded`` (default) or ``captured``
    (browser 3D viewer screenshot).  Syncs the sidecar.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    # Validate content-type / extension
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    suffix = Path(file.filename or "").suffix.lower()
    if content_type not in _ALLOWED_IMAGE_TYPES and suffix not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported image type.  Allowed: png, jpg, jpeg, webp, gif.",
        )

    # Derive a safe extension (prefer from extension; fall back to content-type)
    if suffix in _ALLOWED_IMAGE_EXTS:
        safe_ext = suffix
    else:
        ct_to_ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        safe_ext = ct_to_ext.get(content_type, ".jpg")

    # Generate a unique filename to avoid collisions / path traversal
    unique_stem = secrets.token_hex(8)
    file_prefix = "capture" if source == "captured" else "upload"
    safe_filename = f"{file_prefix}_{unique_stem}{safe_ext}"

    # Write into item_dir/images/
    item_dir = Path(item.dir_path)
    images_dir = item_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / safe_filename
    rel_path = str(dest.relative_to(item_dir))

    # Path traversal guard (should be impossible with safe_filename but be defensive)
    try:
        dest.resolve().relative_to(item_dir.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
        ) from exc

    data = await file.read()
    dest.write_bytes(data)

    # Validate and resolve the source value
    _source = ImageSource.uploaded
    if source == "captured":
        _source = ImageSource.captured

    # Determine order (after all existing images)
    order_result = await db.execute(
        sa.select(sa.func.max(Image.order)).where(Image.item_id == item.id)
    )
    max_order = order_result.scalar_one_or_none()
    new_order = (max_order or 0) + 1

    img = Image(
        item_id=item.id,
        path=rel_path,
        source=_source,
        is_default=False,
        order=new_order,
    )
    db.add(img)
    await db.flush()
    await db.refresh(img)

    item.updated_at = datetime.now(UTC)
    await db.flush()

    await _write_item_sidecar(db, item)

    return ImageOut(
        id=img.id,
        path=img.path,
        source=img.source.value,
        is_default=img.is_default,
        order=img.order,
    )


@router.delete(
    "/{key}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_image(
    key: str,
    image_id: int,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete an image from an item.

    Removes the DB row and (if it exists) the file from the item dir.
    If the deleted image was the default, reassigns default to the first
    remaining image (or leaves none if no images remain).  Syncs the sidecar.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    img_result = await db.execute(
        select(Image).where(Image.id == image_id, Image.item_id == item.id)
    )
    image = img_result.scalar_one_or_none()
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found or does not belong to this item.",
        )

    was_default = image.is_default

    # Remove the on-disk file (best-effort — don't fail if missing)
    try:
        file_path = Path(item.dir_path) / image.path
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except OSError as exc:
        log.warning("delete_image: could not remove file %s: %s", image.path, exc)

    await db.delete(image)
    await db.flush()

    # Reassign default if needed
    if was_default:
        remaining_result = await db.execute(
            select(Image).where(Image.item_id == item.id).order_by(Image.order).limit(1)
        )
        first_remaining = remaining_result.scalar_one_or_none()
        if first_remaining is not None:
            await db.execute(
                sa.update(Image).where(Image.item_id == item.id).values(is_default=False)
            )
            await db.execute(
                sa.update(Image).where(Image.id == first_remaining.id).values(is_default=True)
            )
            item.default_image_id = first_remaining.id
        else:
            item.default_image_id = None

    item.updated_at = datetime.now(UTC)
    await db.flush()

    await _write_item_sidecar(db, item)
