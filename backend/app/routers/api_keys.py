"""Per-user API key management endpoints.

GET    /api/api-keys            → list current user's keys (no raw values)
POST   /api/api-keys            → create a new key (raw returned once)
DELETE /api/api-keys/{key_id}   → revoke a key
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.api_key_auth import generate_raw_key, hash_key
from ..auth.deps import csrf_protect, get_current_user, get_db
from ..models.api_key import ApiKey
from ..models.user import User

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ApiKeySummary(BaseModel):
    id: int
    label: str
    is_active: bool
    last_used_at: str | None = None


class CreateApiKeyRequest(BaseModel):
    label: str


class CreateApiKeyResponse(BaseModel):
    id: int
    label: str
    key: str  # raw key, shown once


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ApiKeySummary])
async def list_api_keys(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiKeySummary]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.id)
    )
    keys = result.scalars().all()
    return [
        ApiKeySummary(
            id=k.id,
            label=k.label,
            is_active=k.is_active,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
        )
        for k in keys
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateApiKeyResponse)
async def create_api_key(
    body: CreateApiKeyRequest,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateApiKeyResponse:
    """Create a new API key.  The raw key is returned once and not stored."""
    raw = generate_raw_key()
    api_key = ApiKey(
        user_id=user.id,
        label=body.label,
        key_hash=hash_key(raw),
    )
    db.add(api_key)
    await db.flush()
    return CreateApiKeyResponse(id=api_key.id, label=api_key.label, key=raw)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: int,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    api_key.is_active = False
