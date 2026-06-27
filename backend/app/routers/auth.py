"""Auth endpoints.

POST /api/auth/login   → validate credentials, set session cookie
POST /api/auth/logout  → invalidate session, clear cookie
GET  /api/auth/me      → return current user info
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.csrf import clear_csrf_cookie, set_csrf_cookie
from ..auth.deps import get_current_user, get_db
from ..auth.provider import PasswordAuthProvider
from ..auth.sessions import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    create_session,
    invalidate_session,
    set_session_cookie,
)
from ..config import settings
from ..models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    ok: bool
    user_id: int
    email: str
    name: str
    role: str


class MeResponse(BaseModel):
    user_id: int
    email: str
    name: str
    role: str
    theme_pref: str
    is_active: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """Authenticate with email + password.  Sets session cookie on success."""
    provider = PasswordAuthProvider(db)
    user_id = await provider.authenticate(body.email, body.password)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Resolve the full user object for the response
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    session_token, csrf_token = await create_session(db, user_id)
    set_session_cookie(response, session_token, secure=settings.COOKIE_SECURE)
    set_csrf_cookie(response, csrf_token, secure=settings.COOKIE_SECURE)

    return LoginResponse(
        ok=True,
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    """Invalidate the session cookie and clear cookies."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await invalidate_session(db, token)
    clear_session_cookie(response)
    clear_csrf_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> MeResponse:
    """Return the currently authenticated user."""
    return MeResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        theme_pref=user.theme_pref,
        is_active=user.is_active,
    )
