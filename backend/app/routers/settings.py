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

Per-user dashboard layout (Phase 12):
  GET   /api/me/dashboard    → get dashboard layout (resolved by role when unset)
  PUT   /api/me/dashboard    → set dashboard layout
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_current_user, get_db, require_admin
from ..models.library import Library
from ..models.setting import Setting
from ..models.user import User
from ..services.settings_service import TAGS_AUTO_APPROVE_KEY

router = APIRouter(tags=["settings"])

_VALID_THEMES = {"system", "light", "dark"}
_VALID_LAYOUTS = {"top", "side"}
_VALID_RENDER_MODES = {"all", "no_images", "off"}

# Per-key value validators: key → set of allowed string values.
_KEY_ALLOWED_VALUES: dict[str, set[str]] = {
    "render.mode": _VALID_RENDER_MODES,
}

# Keys whose value MUST be a JSON boolean (true/false).  Stored/read via
# services.settings_service.get_bool_setting.
_BOOL_KEYS: set[str] = {TAGS_AUTO_APPROVE_KEY}


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


class DashboardStatsLayout(BaseModel):
    density: str = "comfortable"  # 'comfortable' | 'compact'
    tiles: list[str] = []


class DashboardRailLayout(BaseModel):
    collapsed: bool = False
    widgets: list[str] = []


class DashboardLayout(BaseModel):
    stats: DashboardStatsLayout
    rail: DashboardRailLayout


class DashboardLayoutResponse(BaseModel):
    dashboard_layout: DashboardLayout


class DashboardLayoutUpdateRequest(BaseModel):
    dashboard_layout: DashboardLayout


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
    # Per-key value validation
    if key in _KEY_ALLOWED_VALUES:
        allowed = _KEY_ALLOWED_VALUES[key]
        if not isinstance(body.value, str) or body.value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid value for {key!r}: {body.value!r}. "
                    f"Must be one of {sorted(allowed)}."
                ),
            )

    # Boolean-typed keys: reject anything that is not a real JSON boolean.  bool is
    # a subclass of int, so this check must come before any int handling.
    if key in _BOOL_KEYS and not isinstance(body.value, bool):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid value for {key!r}: must be a boolean (true or false).",
        )

    # import.default_library_id: must be int (or null) referencing an enabled library.
    # Explicitly exclude bool: bool is a subclass of int in Python, so isinstance(True, int)
    # is True — we must reject it explicitly.
    if key == "import.default_library_id":
        if body.value is not None:
            if not isinstance(body.value, int) or isinstance(body.value, bool):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="import.default_library_id must be an integer or null.",
                )
            lib_res = await db.execute(
                select(Library).where(
                    Library.id == body.value, Library.enabled.is_(True)
                )
            )
            if lib_res.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Library {body.value} not found or not enabled.",
                )

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


# ---------------------------------------------------------------------------
# Per-user dashboard layout (Phase 12)
# ---------------------------------------------------------------------------

# Default tile sets by role (ordered widget IDs)
_ADMIN_DEFAULT_TILES = [
    "total-assets",
    "prints-done",
    "filament-used",
    "success-rate",
    "jobs-running",
    "pending-reviews",
    "open-issues",
    "pending-tags",
]

_USER_DEFAULT_TILES = [
    "total-assets",
    "prints-done",
    "filament-used",
    "success-rate",
    "jobs-running",
]

_DEFAULT_RAIL_WIDGETS = ["quick-import"]


def _resolve_dashboard_layout(db_user: User) -> DashboardLayout:
    """Return the effective dashboard layout, resolving to role default when unset."""
    if db_user.dashboard_layout:
        try:
            raw = json.loads(db_user.dashboard_layout)
            return DashboardLayout(
                stats=DashboardStatsLayout(**raw.get("stats", {})),
                rail=DashboardRailLayout(**raw.get("rail", {})),
            )
        except Exception:
            pass  # malformed JSON → fall through to role default

    is_admin = db_user.role.value == "admin"
    return DashboardLayout(
        stats=DashboardStatsLayout(
            density="compact" if is_admin else "comfortable",
            tiles=_ADMIN_DEFAULT_TILES if is_admin else _USER_DEFAULT_TILES,
        ),
        rail=DashboardRailLayout(
            collapsed=False,
            widgets=_DEFAULT_RAIL_WIDGETS,
        ),
    )


@router.get("/api/me/dashboard", response_model=DashboardLayoutResponse)
async def get_dashboard_layout(
    user: Annotated[User, Depends(get_current_user)],
) -> DashboardLayoutResponse:
    """Get the current user's dashboard layout (resolved to role default when unset).

    Admin default: compact density + admin stat tiles (pending-reviews, open-issues,
    pending-tags) + quick-import rail.
    User default: comfortable density + basic stat tiles + quick-import rail.
    """
    return DashboardLayoutResponse(dashboard_layout=_resolve_dashboard_layout(user))


@router.put("/api/me/dashboard", response_model=DashboardLayoutResponse)
async def update_dashboard_layout(
    body: DashboardLayoutUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardLayoutResponse:
    """Set the current user's dashboard layout.

    Shape: { stats: { density, tiles[] }, rail: { collapsed, widgets[] } }
    Pass the full layout object; partial updates not supported (replace-on-write).
    """
    from sqlalchemy import select as sa_select

    # Validate density
    if body.dashboard_layout.stats.density not in ("comfortable", "compact"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid density: {body.dashboard_layout.stats.density!r}. "
                "Must be 'comfortable' or 'compact'."
            ),
        )

    result = await db.execute(sa_select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.dashboard_layout = body.dashboard_layout.model_dump_json()
    await db.flush()
    return DashboardLayoutResponse(dashboard_layout=_resolve_dashboard_layout(db_user))
