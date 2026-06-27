"""FastAPI dependency injection helpers for auth.

get_db        → yields an AsyncSession
get_current_user   → requires valid session cookie OR Bearer API key
require_admin      → requires admin role
csrf_protect       → validates CSRF token on state-changing requests

Usage in route handlers:
    @router.post("/example")
    async def example(
        user: Annotated[User, Depends(get_current_user)],
        _csrf: Annotated[None, Depends(csrf_protect)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> ...:
        ...
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal
from ..models.user import User, UserRole
from .api_key_auth import get_api_key_record
from .csrf import CSRF_HEADER_NAME
from .sessions import SESSION_COOKIE_NAME, get_session

# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------


async def get_db() -> AsyncSession:  # type: ignore[return]
    """Yield an AsyncSession and commit/rollback/close on exit."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Current user resolution (session cookie OR Bearer API key)
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve the authenticated User from cookie session OR Bearer token.

    Priority:
      1. Authorization: Bearer <key>  (API-key requests — CSRF exempt)
      2. Session cookie               (browser requests — CSRF enforced separately)

    Raises 401 if neither method resolves to a valid user.
    """
    # --- 1. Bearer token ---
    auth_header: str | None = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        raw = auth_header[len("Bearer "):]
        api_key = await get_api_key_record(db, raw)
        if api_key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        result = await db.execute(
            select(User).where(User.id == api_key.user_id, User.is_active.is_(True))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        # Update last_used_at asynchronously; flush within same unit of work.
        from datetime import UTC, datetime

        api_key.last_used_at = datetime.now(UTC)
        return user

    # --- 2. Session cookie ---
    session_token: str | None = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        session = await get_session(db, session_token)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
            )
        result = await db.execute(
            select(User).where(User.id == session.user_id, User.is_active.is_(True))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------------------------------------------
# Role guard
# ---------------------------------------------------------------------------


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency that requires the current user to be an admin."""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# CSRF protection for cookie-authenticated state-changing requests
# ---------------------------------------------------------------------------


async def csrf_protect(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Validate CSRF double-submit for cookie-authenticated requests.

    Skips validation if the request uses a Bearer token (API-key requests are
    CSRF-exempt).  Raises 403 for cookie-authenticated state-changing requests
    that are missing or have a mismatched CSRF token.
    """
    # Skip for safe methods
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # Skip for Bearer-authenticated requests (not cookie-based).
    auth_header: str | None = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return

    # No session cookie → auth will fail anyway; don't double-error here.
    session_token: str | None = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return

    session = await get_session(db, session_token)
    if session is None:
        return  # auth dependency will catch this

    header_csrf: str | None = request.headers.get(CSRF_HEADER_NAME)
    if not header_csrf:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing {CSRF_HEADER_NAME} header",
        )

    import hmac

    if not hmac.compare_digest(header_csrf, session.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )
