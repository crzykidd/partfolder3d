"""First-run setup endpoints.

GET  /api/setup/status  → { initialized: bool }
POST /api/setup          → create admin + instance basics (only while uninitialized)

Once at least one user exists, POST /api/setup returns 409 Conflict.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.csrf import set_csrf_cookie
from ..auth.deps import get_db
from ..auth.password import hash_password
from ..auth.sessions import create_session, set_session_cookie
from ..config import settings
from ..models.user import User, UserRole

router = APIRouter(prefix="/api/setup", tags=["setup"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SetupStatusResponse(BaseModel):
    initialized: bool


class SetupRequest(BaseModel):
    admin_email: EmailStr
    admin_name: str
    admin_password: str
    instance_name: str = "PartFolder 3D"
    external_url: str = ""
    timezone: str = "UTC"


class SetupResponse(BaseModel):
    ok: bool
    user_id: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _is_initialized(db: AsyncSession) -> bool:
    result = await db.execute(select(func.count()).select_from(User))
    return (result.scalar() or 0) > 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: Annotated[AsyncSession, Depends(get_db)]) -> SetupStatusResponse:
    """Return whether the instance has been initialized (admin exists)."""
    return SetupStatusResponse(initialized=await _is_initialized(db))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SetupResponse)
async def run_setup(
    body: SetupRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SetupResponse:
    """Create the initial admin user and instance settings.

    Locked once initialized — subsequent calls return 409.
    """
    if await _is_initialized(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Instance already initialized",
        )

    if len(body.admin_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    # Create admin user
    user = User(
        email=body.admin_email,
        name=body.admin_name,
        role=UserRole.admin,
        password_hash=hash_password(body.admin_password),
    )
    db.add(user)
    await db.flush()

    # Persist instance settings
    import json

    from ..models.setting import Setting

    for key, value in [
        ("instance.name", body.instance_name),
        ("instance.external_url", body.external_url),
        ("instance.timezone", body.timezone),
    ]:
        db.add(Setting(key=key, value=json.dumps(value)))

    await db.flush()

    # Auto-login the new admin.
    session_token, csrf_token = await create_session(db, user.id)
    set_session_cookie(response, session_token, secure=settings.COOKIE_SECURE)
    set_csrf_cookie(response, csrf_token, secure=settings.COOKIE_SECURE)

    # Commit explicitly here so the session row is durable in the DB before
    # this function returns.  FastAPI's get_db dependency also commits after the
    # yield (which runs after the response object is built but before bytes are
    # sent), so this is belt-and-suspenders: it ensures a near-instant follow-up
    # GET /api/auth/me can never race a still-pending commit.  A redundant
    # commit on an already-committed session is a harmless no-op in SQLAlchemy.
    await db.commit()

    return SetupResponse(ok=True, user_id=user.id)
