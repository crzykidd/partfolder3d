"""Server-side session management.

Sessions are opaque tokens stored in the `user_sessions` table.
The token is delivered as an httpOnly cookie (name: SESSION_COOKIE_NAME).

Cookie flags:
  - httpOnly: True   (JS cannot read the token)
  - samesite: "lax"  (protects against CSRF for top-level navigations)
  - secure: settings.COOKIE_SECURE  (True in prod; False for local http dev)

See docs/decisions.md for the DB-vs-Redis session store decision.
"""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.session import SESSION_LIFETIME_DAYS, UserSession
from .csrf import generate_csrf_token

SESSION_COOKIE_NAME = "pf3d_session"
_TOKEN_BYTES = 32  # 256 bits of entropy


async def create_session(db: AsyncSession, user_id: int) -> tuple[str, str]:
    """Create a new session row and return (raw_token, csrf_token)."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    csrf_token = generate_csrf_token()
    expires_at = datetime.now(UTC) + timedelta(days=SESSION_LIFETIME_DAYS)
    session = UserSession(
        user_id=user_id, token=token, csrf_token=csrf_token, expires_at=expires_at
    )
    db.add(session)
    await db.flush()  # assign id without committing (caller commits)
    return token, csrf_token


async def get_session(db: AsyncSession, token: str) -> UserSession | None:
    """Look up an active, non-expired session by its raw token.

    Returns None if the session is missing, inactive, or expired.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(UserSession).where(
            UserSession.token == token,
            UserSession.is_active.is_(True),
            UserSession.expires_at > now,
        )
    )
    return result.scalar_one_or_none()


async def invalidate_session(db: AsyncSession, token: str) -> None:
    """Mark a session as inactive (logout)."""
    result = await db.execute(
        select(UserSession).where(UserSession.token == token)
    )
    session = result.scalar_one_or_none()
    if session:
        session.is_active = False
        await db.flush()


def set_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    """Attach the session cookie to *response*."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=SESSION_LIFETIME_DAYS * 86400,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Delete the session cookie on *response*."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", httponly=True, samesite="lax")


def get_session_token_from_request(request: Request) -> str | None:
    """Extract the raw session token from the request cookies."""
    return request.cookies.get(SESSION_COOKIE_NAME)
