"""Settings endpoints.

Admin:
  GET   /api/settings        → get all settings
  PUT   /api/settings/{key}  → create/update a setting

Per-user theme:
  GET   /api/me/theme        → get current user's theme
  PUT   /api/me/theme        → update current user's theme

Per-user nav layout:
  GET   /api/me/nav-layout   → get nav layout preference (resolved by role when unset)
  PUT   /api/me/nav-layout   → set nav layout preference ('top' | 'side')
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_current_user, get_db, require_admin
from ..models.setting import Setting
from ..models.user import User

router = APIRouter(tags=["settings"])

_VALID_THEMES = {"system", "light", "dark"}
_VALID_LAYOUTS = {"top", "side"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SettingOut(BaseModel):
    key: str
    value: Any  # parsed JSON value


class SetSettingRequest(BaseModel):
    value: Any  # any JSON-serializable value


class ThemeResponse(BaseModel):
    theme_pref: str


class ThemeUpdateRequest(BaseModel):
    theme_pref: str


class NavLayoutResponse(BaseModel):
    nav_layout: str  # always resolved: 'top' | 'side'


class NavLayoutUpdateRequest(BaseModel):
    nav_layout: str | None = None  # null = reset to role default


# ---------------------------------------------------------------------------
# Instance settings (admin)
# ---------------------------------------------------------------------------


@router.get("/api/settings", response_model=list[SettingOut])
async def list_settings(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SettingOut]:
    result = await db.execute(select(Setting).order_by(Setting.key))
    rows = result.scalars().all()
    return [SettingOut(key=r.key, value=json.loads(r.value)) for r in rows]


@router.put("/api/settings/{key}", response_model=SettingOut)
async def upsert_setting(
    key: str,
    body: SetSettingRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SettingOut:
    value_json = json.dumps(body.value)
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value_json
    else:
        row = Setting(key=key, value=value_json)
        db.add(row)
    await db.flush()
    return SettingOut(key=row.key, value=json.loads(row.value))


# ---------------------------------------------------------------------------
# Per-user theme
# ---------------------------------------------------------------------------


@router.get("/api/me/theme", response_model=ThemeResponse)
async def get_theme(
    user: Annotated[User, Depends(get_current_user)],
) -> ThemeResponse:
    return ThemeResponse(theme_pref=user.theme_pref)


@router.put("/api/me/theme", response_model=ThemeResponse)
async def update_theme(
    body: ThemeUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ThemeResponse:
    if body.theme_pref not in _VALID_THEMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid theme: {body.theme_pref!r}. Must be one of {sorted(_VALID_THEMES)}",
        )
    # Re-fetch within this session's unit of work
    from sqlalchemy import select as sa_select

    result = await db.execute(sa_select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.theme_pref = body.theme_pref
    await db.flush()
    return ThemeResponse(theme_pref=db_user.theme_pref)


# ---------------------------------------------------------------------------
# Per-user nav layout
# ---------------------------------------------------------------------------


def _resolve_nav_layout(db_user: User) -> str:
    """Return the effective nav layout, falling back to role default when unset."""
    if db_user.nav_layout:
        return db_user.nav_layout
    return "side" if db_user.role.value == "admin" else "top"


@router.get("/api/me/nav-layout", response_model=NavLayoutResponse)
async def get_nav_layout(
    user: Annotated[User, Depends(get_current_user)],
) -> NavLayoutResponse:
    """Get the current user's nav layout preference (resolved: 'top' | 'side').

    When unset (null), the default is resolved by role:
      admin → 'side'
      user  → 'top'
    """
    return NavLayoutResponse(nav_layout=_resolve_nav_layout(user))


@router.put("/api/me/nav-layout", response_model=NavLayoutResponse)
async def update_nav_layout(
    body: NavLayoutUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NavLayoutResponse:
    """Set the current user's nav layout preference.

    Pass nav_layout='top' or 'side' to set, or null to reset to the role default.
    """
    from sqlalchemy import select as sa_select

    if body.nav_layout is not None and body.nav_layout not in _VALID_LAYOUTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid nav_layout: {body.nav_layout!r}. "
                f"Must be one of {sorted(_VALID_LAYOUTS)} or null."
            ),
        )
    result = await db.execute(sa_select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.nav_layout = body.nav_layout
    await db.flush()
    return NavLayoutResponse(nav_layout=_resolve_nav_layout(db_user))
