"""Password reset endpoints.

Admin-only:
  POST /api/password-reset              → generate reset token for a user (1-day)
  DELETE /api/password-reset/{reset_id} → revoke a reset token

Public:
  POST /api/password-reset/{token}      → consume token, set new password
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..auth.password import hash_password
from ..models.password_reset import RESET_TOKEN_LIFETIME_HOURS, PasswordResetToken
from ..models.session import UserSession
from ..models.user import User

router = APIRouter(tags=["password-reset"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateResetRequest(BaseModel):
    email: EmailStr


class ResetTokenResponse(BaseModel):
    id: int
    user_id: int
    expires_at: datetime
    token: str | None = None  # only at creation


class UseResetRequest(BaseModel):
    new_password: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------


@router.post(
    "/api/password-reset",
    status_code=status.HTTP_201_CREATED,
    response_model=ResetTokenResponse,
)
async def create_reset_token(
    body: CreateResetRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ResetTokenResponse:
    """Generate a 1-day password reset link for *email*.

    The raw token is returned once for the admin to hand off manually.
    No email delivery in Phase 1 (see PRD §13/17).
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(UTC) + timedelta(hours=RESET_TOKEN_LIFETIME_HOURS)

    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(reset)
    await db.flush()

    return ResetTokenResponse(
        id=reset.id,
        user_id=reset.user_id,
        expires_at=reset.expires_at,
        token=raw_token,
    )


@router.delete("/api/password-reset/{reset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_reset_token(
    reset_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke a password reset token."""
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.id == reset_id)
    )
    reset = result.scalar_one_or_none()
    if reset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reset token not found")
    reset.revoked = True


# ---------------------------------------------------------------------------
# Public route
# ---------------------------------------------------------------------------


@router.post("/api/password-reset/{token}", response_model=dict)
async def use_reset_token(
    token: str,
    body: UseResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    """Consume a reset token and set the user's new password."""
    token_hash = _hash_token(token)
    now = datetime.now(UTC)

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    reset = result.scalar_one_or_none()

    if reset is None or reset.revoked or reset.used:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reset token not found or already used"
        )
    if reset.expires_at < now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Reset token has expired")

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    user_result = await db.execute(select(User).where(User.id == reset.user_id))
    user = user_result.scalar_one()
    user.password_hash = hash_password(body.new_password)
    reset.used = True

    # Invalidate every existing session for this user. A password reset is a
    # recovery/lockout flow (there is no "current" session to preserve — it is
    # driven by the token, not a logged-in cookie), so any previously issued
    # session must stop working the moment the password changes.
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id)
        .values(is_active=False)
    )

    return {"ok": True}
