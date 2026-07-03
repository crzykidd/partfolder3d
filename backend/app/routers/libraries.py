"""Library management endpoints (admin only).

POST   /api/libraries                → register a new library mount
GET    /api/libraries                → list all libraries (with item counts)
DELETE /api/libraries/{lib_id}      → disable (soft-delete) a library
POST   /api/libraries/{lib_id}/enable  → re-enable a disabled library
DELETE /api/libraries/{lib_id}/purge   → hard-delete an empty library
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..models.item import Item
from ..models.library import Library
from ..models.user import User

router = APIRouter(prefix="/api/libraries", tags=["libraries"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LibraryCreate(BaseModel):
    name: str
    mount_path: str


class LibraryOut(BaseModel):
    id: int
    name: str
    mount_path: str
    enabled: bool
    item_count: int = 0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_library_or_404(lib_id: int, db: AsyncSession) -> Library:
    result = await db.execute(select(Library).where(Library.id == lib_id))
    lib = result.scalar_one_or_none()
    if lib is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library not found.")
    return lib


async def _count_items(lib_id: int, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(Item.id)).where(Item.library_id == lib_id)
    )
    return result.scalar_one()


def _lib_out(lib: Library, item_count: int) -> LibraryOut:
    return LibraryOut(
        id=lib.id,
        name=lib.name,
        mount_path=lib.mount_path,
        enabled=lib.enabled,
        item_count=item_count,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=LibraryOut, status_code=status.HTTP_201_CREATED)
async def create_library(
    body: LibraryCreate,
    _user: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryOut:
    """Register a new library mount (admin only)."""
    existing = await db.execute(
        select(Library).where(Library.mount_path == body.mount_path)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Library with mount_path {body.mount_path!r} already exists.",
        )
    lib = Library(name=body.name, mount_path=body.mount_path, enabled=True)
    db.add(lib)
    await db.flush()
    await db.refresh(lib)
    return _lib_out(lib, 0)


@router.get("", response_model=list[LibraryOut])
async def list_libraries(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LibraryOut]:
    """List all registered libraries with per-library asset counts."""
    item_count_sq = (
        select(func.count(Item.id))
        .where(Item.library_id == Library.id)
        .correlate(Library)
        .scalar_subquery()
    )
    result = await db.execute(
        select(Library, item_count_sq.label("item_count")).order_by(Library.id)
    )
    return [_lib_out(lib, count) for lib, count in result.all()]


@router.delete("/{lib_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def disable_library(
    lib_id: int,
    _user: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Disable (soft-delete) a library.  Items are NOT deleted."""
    lib = await _get_library_or_404(lib_id, db)
    lib.enabled = False
    await db.flush()


@router.post("/{lib_id}/enable", response_model=LibraryOut)
async def enable_library(
    lib_id: int,
    _user: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryOut:
    """Re-enable a soft-disabled library."""
    lib = await _get_library_or_404(lib_id, db)
    lib.enabled = True
    await db.flush()
    item_count = await _count_items(lib_id, db)
    return _lib_out(lib, item_count)


@router.delete("/{lib_id}/purge", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def purge_library(
    lib_id: int,
    _user: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Hard-delete an empty library (no items).

    Returns 409 if the library still has assets — move or remove them first.
    The on-disk library directory is NOT removed here (no filesystem management
    exists in the disable path either); the operator removes the volume when ready.
    """
    lib = await _get_library_or_404(lib_id, db)
    item_count = await _count_items(lib_id, db)
    if item_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Library '{lib.name}' still has {item_count} asset(s). "
                "Move or remove all assets before deleting the library. "
                "Move-between-libraries support is tracked in issue #25."
            ),
        )
    await db.delete(lib)
    await db.flush()
