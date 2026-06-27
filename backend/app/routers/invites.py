"""Invite management endpoints.

Admin-only management:
  POST   /api/invites                   → create invite (7-day token)
  GET    /api/invites                   → list all invites with status
  DELETE /api/invites/{invite_id}       → revoke an invite

Public:
  POST   /api/invites/{token}/accept    → accept invite (creates user)
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..auth.password import hash_password
from ..models.invite import INVITE_LIFETIME_DAYS, Invite, InviteStatus
from ..models.user import User

router = APIRouter(tags=["invites"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateInviteRequest(BaseModel):
    email: EmailStr


class InviteResponse(BaseModel):
    id: int
    email: str
    status: str
    expires_at: datetime
    token: str | None = None  # only present at creation
    created_at: datetime


class AcceptInviteRequest(BaseModel):
    name: str
    password: str


class AcceptInviteResponse(BaseModel):
    ok: bool
    user_id: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------


@router.post(
    "/api/invites",
    status_code=status.HTTP_201_CREATED,
    response_model=InviteResponse,
)
async def create_invite(
    body: CreateInviteRequest,
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InviteResponse:
    """Create a 7-day invite link for *email*."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(UTC) + timedelta(days=INVITE_LIFETIME_DAYS)

    invite = Invite(
        token_hash=token_hash,
        email=body.email,
        created_by_id=admin.id,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.flush()

    return InviteResponse(
        id=invite.id,
        email=invite.email,
        status=invite.status.value,
        expires_at=invite.expires_at,
        token=raw_token,  # shown once
        created_at=invite.created_at,
    )


@router.get("/api/invites", response_model=list[InviteResponse])
async def list_invites(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InviteResponse]:
    """List all invites with their current status."""
    now = datetime.now(UTC)
    result = await db.execute(select(Invite).order_by(Invite.created_at.desc()))
    invites = result.scalars().all()

    out = []
    for inv in invites:
        # Auto-expire pending invites that have passed their deadline
        if inv.status == InviteStatus.pending and inv.expires_at < now:
            inv.status = InviteStatus.expired
        out.append(
            InviteResponse(
                id=inv.id,
                email=inv.email,
                status=inv.status.value,
                expires_at=inv.expires_at,
                token=None,  # never re-shown
                created_at=inv.created_at,
            )
        )
    return out


@router.delete("/api/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    invite_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke an invite."""
    result = await db.execute(select(Invite).where(Invite.id == invite_id))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.status not in (InviteStatus.pending,):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invite is already {invite.status.value}",
        )
    invite.status = InviteStatus.revoked


# ---------------------------------------------------------------------------
# Public route
# ---------------------------------------------------------------------------


@router.post(
    "/api/invites/{token}/accept",
    status_code=status.HTTP_201_CREATED,
    response_model=AcceptInviteResponse,
)
async def accept_invite(
    token: str,
    body: AcceptInviteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcceptInviteResponse:
    """Accept an invite: set name + password, create the user account."""
    token_hash = _hash_token(token)
    now = datetime.now(UTC)

    result = await db.execute(select(Invite).where(Invite.token_hash == token_hash))
    invite = result.scalar_one_or_none()

    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.status != InviteStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invite is {invite.status.value}",
        )
    if invite.expires_at < now:
        invite.status = InviteStatus.expired
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite has expired")

    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    # Check if email already registered
    existing = await db.execute(select(User).where(User.email == invite.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(
        email=invite.email,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    invite.status = InviteStatus.accepted
    invite.accepted_at = now

    return AcceptInviteResponse(ok=True, user_id=user.id)
