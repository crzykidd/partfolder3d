"""Per-user printer profiles (presets for the Log-print form).

GET    /api/me/printer-profiles         → list (default first, then by name)
POST   /api/me/printer-profiles         → create (409 on duplicate name)
PATCH  /api/me/printer-profiles/{id}    → partial update (incl. is_default)
DELETE /api/me/printer-profiles/{id}    → 204

All endpoints require authentication; mutations are CSRF-protected. Every
query is scoped to the current user (another user's id → 404). Setting a
profile as default clears the user's other defaults in the same transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_current_user, get_db
from ..models.printer_profile import PrinterProfile
from ..models.user import User

router = APIRouter(tags=["printer-profiles"])

_SETTINGS_FIELDS = (
    "printer",
    "material",
    "filament_color",
    "nozzle_diameter",
    "layer_height",
    "supports",
)


class PrinterProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    printer: str | None = None
    material: str | None = None
    filament_color: str | None = None
    nozzle_diameter: float | None = None
    layer_height: float | None = None
    supports: bool | None = None
    is_default: bool = False


class PrinterProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    printer: str | None = None
    material: str | None = None
    filament_color: str | None = None
    nozzle_diameter: float | None = None
    layer_height: float | None = None
    supports: bool | None = None
    is_default: bool | None = None


class PrinterProfileOut(BaseModel):
    id: int
    name: str
    printer: str | None
    material: str | None
    filament_color: str | None
    nozzle_diameter: float | None
    layer_height: float | None
    supports: bool | None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _duplicate() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A printer profile with that name already exists.",
    )


async def _get_owned(db: AsyncSession, user: User, profile_id: int) -> PrinterProfile:
    result = await db.execute(
        select(PrinterProfile).where(
            PrinterProfile.id == profile_id, PrinterProfile.user_id == user.id
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Printer profile not found."
        )
    return profile


async def _clear_defaults(db: AsyncSession, user: User, except_id: int | None) -> None:
    stmt = update(PrinterProfile).where(
        PrinterProfile.user_id == user.id, PrinterProfile.is_default.is_(True)
    )
    if except_id is not None:
        stmt = stmt.where(PrinterProfile.id != except_id)
    await db.execute(stmt.values(is_default=False))


@router.get("/api/me/printer-profiles", response_model=list[PrinterProfileOut])
async def list_printer_profiles(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PrinterProfile]:
    result = await db.execute(
        select(PrinterProfile)
        .where(PrinterProfile.user_id == user.id)
        .order_by(PrinterProfile.is_default.desc(), PrinterProfile.name, PrinterProfile.id)
    )
    return list(result.scalars().all())


@router.post(
    "/api/me/printer-profiles",
    response_model=PrinterProfileOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_printer_profile(
    body: PrinterProfileIn,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterProfile:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name must not be blank.")
    dup = await db.execute(
        select(PrinterProfile.id).where(
            PrinterProfile.user_id == user.id, PrinterProfile.name == name
        )
    )
    if dup.scalar_one_or_none() is not None:
        raise _duplicate()

    if body.is_default:
        await _clear_defaults(db, user, None)
    profile = PrinterProfile(
        user_id=user.id,
        name=name,
        is_default=body.is_default,
        **{f: getattr(body, f) for f in _SETTINGS_FIELDS},
    )
    db.add(profile)
    try:
        await db.flush()
    except IntegrityError:
        raise _duplicate() from None
    await db.refresh(profile)
    return profile


@router.patch("/api/me/printer-profiles/{profile_id}", response_model=PrinterProfileOut)
async def update_printer_profile(
    profile_id: int,
    body: PrinterProfilePatch,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterProfile:
    profile = await _get_owned(db, user, profile_id)
    data = body.model_dump(exclude_unset=True)

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name must not be blank.")
        if name != profile.name:
            dup = await db.execute(
                select(PrinterProfile.id).where(
                    PrinterProfile.user_id == user.id,
                    PrinterProfile.name == name,
                    PrinterProfile.id != profile.id,
                )
            )
            if dup.scalar_one_or_none() is not None:
                raise _duplicate()
        profile.name = name

    for f in _SETTINGS_FIELDS:
        if f in data:
            setattr(profile, f, data[f])

    if "is_default" in data and data["is_default"] is not None:
        if data["is_default"]:
            await _clear_defaults(db, user, profile.id)
        profile.is_default = data["is_default"]

    try:
        await db.flush()
    except IntegrityError:
        raise _duplicate() from None
    await db.refresh(profile)
    return profile


@router.delete(
    "/api/me/printer-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_printer_profile(
    profile_id: int,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    profile = await _get_owned(db, user, profile_id)
    await db.delete(profile)
    await db.flush()
