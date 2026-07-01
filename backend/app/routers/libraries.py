"""Library management endpoints (admin only).

POST   /api/libraries           → register a new library mount
GET    /api/libraries           → list all libraries
DELETE /api/libraries/{lib_id} → disable (soft-delete) a library
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
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

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=LibraryOut, status_code=status.HTTP_201_CREATED)
async def create_library(
    body: LibraryCreate,
    _user: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Library:
    """Register a new library mount (admin only)."""
    # Check for duplicate mount_path
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
    return lib


@router.get("", response_model=list[LibraryOut])
async def list_libraries(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Library]:
    """List all registered libraries."""
    result = await db.execute(select(Library).order_by(Library.id))
    return list(result.scalars().all())


@router.delete("/{lib_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def disable_library(
    lib_id: int,
    _user: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Disable (soft-delete) a library.  Items are NOT deleted."""
    result = await db.execute(select(Library).where(Library.id == lib_id))
    lib = result.scalar_one_or_none()
    if lib is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library not found.")
    lib.enabled = False
    await db.flush()
