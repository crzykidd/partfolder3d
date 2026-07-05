"""Item file management: upload, delete, rename (issues #18 / #19).

POST   /api/items/{key}/files             → upload an additional file
DELETE /api/items/{key}/files/{file_id}   → delete a file
PATCH  /api/items/{key}/files/{file_id}   → rename a file (basename only)

Split out of the former monolithic ``routers/items.py`` (audit §D); routes,
paths, methods, and response models are unchanged.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
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
from ...models.file import File
from ...models.item import Item
from ...models.user import User
from ...services.item_helpers import (
    _enqueue_analyze,
    _enqueue_render,
    _write_item_sidecar,
)
from ...storage.inventory import hash_file_sha256, infer_role
from ...worker.arq_pool import get_arq_pool
from .schemas import FileOut, RenameFileRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["items"])


_ALLOWED_FILE_EXTENSIONS = frozenset({
    # 3D model formats
    ".stl", ".3mf", ".obj", ".ply", ".blend", ".f3d",
    ".step", ".stp", ".fcstd", ".amf", ".dae",
    # Archive
    ".zip",
    # G-code
    ".gcode", ".gco", ".bgcode",
    # Documents / project notes
    ".pdf", ".txt", ".md",
})


@router.post(
    "/{key}/files",
    response_model=FileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    key: str,
    file: Annotated[UploadFile, FastAPIFile(...)],
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> FileOut:
    """Upload an additional file to an existing item.

    Accepts model formats, archives, and g-code.  Saves the file into the item
    directory root with a sanitized, collision-safe filename.  Creates a File row,
    syncs the sidecar, and enqueues analyze + render (3MF skips render via the
    model_extensions guard in _enqueue_render).
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported file type {suffix!r}. "
                f"Allowed: {', '.join(sorted(_ALLOWED_FILE_EXTENSIONS))}"
            ),
        )

    # Derive a safe filename from the uploaded name.
    original_stem = Path(file.filename or "upload").stem
    safe_stem = re.sub(r"[^\w.\-]", "_", original_stem)[:200] or "upload"
    safe_filename = f"{safe_stem}{suffix}"

    item_dir = Path(item.dir_path)
    dest = item_dir / safe_filename
    counter = 1
    while dest.exists():
        dest = item_dir / f"{safe_stem}_{counter}{suffix}"
        counter += 1

    rel_path = str(dest.relative_to(item_dir))

    # Path traversal guard (belt-and-suspenders after safe_stem construction).
    try:
        dest.resolve().relative_to(item_dir.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path."
        ) from exc

    data = await file.read()
    dest.write_bytes(data)

    stat = dest.stat()
    sha256 = hash_file_sha256(dest)
    role = infer_role(rel_path)
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    size = stat.st_size

    f = File(
        item_id=item.id,
        path=rel_path,
        role=role,
        size=size,
        sha256=sha256,
        mtime=mtime,
        last_seen_size=size,
        last_seen_mtime=mtime,
    )
    db.add(f)
    await db.flush()
    await db.refresh(f)

    item.updated_at = datetime.now(UTC)
    await db.flush()

    await _write_item_sidecar(db, item)

    await _enqueue_analyze(item.id, pool=arq, db=db)
    await _enqueue_render(item.id, pool=arq, db=db, model_extensions=[suffix])

    return FileOut(
        id=f.id,
        path=f.path,
        role=f.role.value,
        size=f.size,
        sha256=f.sha256,
        object_analysis=None,
    )


@router.delete(
    "/{key}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_file(
    key: str,
    file_id: int,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a single file from an item.

    Removes the DB row and (if it exists on disk) the physical file.
    Syncs the sidecar.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    file_result = await db.execute(
        select(File).where(File.id == file_id, File.item_id == item.id)
    )
    f = file_result.scalar_one_or_none()
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or does not belong to this item.",
        )

    # Remove the on-disk file (best-effort — don't fail if already missing).
    try:
        file_path = Path(item.dir_path) / f.path
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except OSError as exc:
        log.warning("delete_file: could not remove file %s: %s", f.path, exc)

    await db.delete(f)
    item.updated_at = datetime.now(UTC)
    await db.flush()

    await _write_item_sidecar(db, item)


@router.patch(
    "/{key}/files/{file_id}",
    response_model=FileOut,
)
async def rename_file(
    key: str,
    file_id: int,
    body: RenameFileRequest,
    _user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileOut:
    """Rename a file (new basename only — file stays in its current directory).

    Updates the on-disk file and the files.path DB column.  Re-infers role from
    the new extension.  Syncs the sidecar.  The new name must be a plain filename
    with no path separators or traversal components.
    """
    result = await db.execute(
        select(Item).options(selectinload(Item.creator)).where(Item.key == key)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    file_result = await db.execute(
        select(File).where(File.id == file_id, File.item_id == item.id)
    )
    f = file_result.scalar_one_or_none()
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or does not belong to this item.",
        )

    new_name = body.name.strip()

    if not new_name or "/" in new_name or "\\" in new_name or ".." in new_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid filename: must be a plain name with no path separators.",
        )
    if len(new_name) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filename too long (max 255 characters).",
        )

    item_dir = Path(item.dir_path)
    old_abs = item_dir / f.path

    # New path: same parent directory as the current file.
    parent = Path(f.path).parent
    new_rel = str(parent / new_name)
    new_abs = item_dir / new_rel

    # Path traversal guard.
    try:
        new_abs.resolve().relative_to(item_dir.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
        ) from exc

    # Collision guard.
    if new_abs.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A file named {new_name!r} already exists in this location.",
        )

    # Rename on disk (atomic on same filesystem).
    if old_abs.exists():
        try:
            old_abs.rename(new_abs)
        except OSError as exc:
            log.exception("rename_file: failed to rename %s on disk", f.path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to rename file on disk.",
            ) from exc
    else:
        log.warning(
            "rename_file: source %s not found on disk — updating DB path only", f.path
        )

    f.path = new_rel
    f.role = infer_role(new_rel)
    item.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(f)

    await _write_item_sidecar(db, item)

    return FileOut(
        id=f.id,
        path=f.path,
        role=f.role.value,
        size=f.size,
        sha256=f.sha256,
        object_analysis=f.object_analysis,
    )
