"""AI provider CRUD endpoints — admin-only (Phase 8).

GET    /api/ai-providers              → list all providers (keys masked)
POST   /api/ai-providers              → create a provider
GET    /api/ai-providers/{id}         → get one provider (key masked)
PATCH  /api/ai-providers/{id}         → update provider (optionally rotate key)
DELETE /api/ai-providers/{id}         → delete provider
POST   /api/ai-providers/{id}/enable  → toggle enabled flag
POST   /api/ai-providers/test         → test connection (key NOT persisted)

All endpoints require admin role. Keys are write-only: stored Fernet-encrypted
and never returned in any response. ``has_key`` indicates whether a key is set.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..crypto import encrypt
from ..models.ai_provider import AiProvider, AiProviderType
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-providers", tags=["ai"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AiProviderOut(BaseModel):
    id: int
    provider: str
    endpoint: str | None
    model: str | None
    has_key: bool  # True when api_key_encrypted is set — the key itself is never returned
    enabled: bool

    model_config = {"from_attributes": False}


class CreateAiProviderRequest(BaseModel):
    provider: str  # "claude" | "openai" | "ollama"
    endpoint: str | None = None
    model: str | None = None
    api_key: str | None = None  # plaintext — encrypted before storage; write-only
    enabled: bool = False


class PatchAiProviderRequest(BaseModel):
    endpoint: str | None = None
    model: str | None = None
    api_key: str | None = None  # if provided, rotates the stored key
    enabled: bool | None = None


class EnableRequest(BaseModel):
    enabled: bool


class TestConnectionRequest(BaseModel):
    provider: str
    endpoint: str | None = None
    model: str | None = None
    api_key: str | None = None  # plaintext — NOT persisted; used for the test call only


class TestConnectionResponse(BaseModel):
    ok: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_provider_type(value: str) -> AiProviderType:
    try:
        return AiProviderType(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid provider type: {value!r}. "
                "Must be one of: claude, openai, ollama"
            ),
        ) from exc


def _to_out(p: AiProvider) -> AiProviderOut:
    return AiProviderOut(
        id=p.id,
        provider=p.provider.value,
        endpoint=p.endpoint,
        model=p.model,
        has_key=bool(p.api_key_encrypted),
        enabled=p.enabled,
    )


async def _get_or_404(provider_id: int, db: AsyncSession) -> AiProvider:
    result = await db.execute(
        select(AiProvider).where(AiProvider.id == provider_id)
    )
    p = result.scalar_one_or_none()
    if p is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI provider not found.",
        )
    return p


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AiProviderOut])
async def list_ai_providers(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AiProviderOut]:
    """List all configured AI providers (admin only). Keys are never returned."""
    result = await db.execute(select(AiProvider).order_by(AiProvider.id))
    return [_to_out(p) for p in result.scalars().all()]


@router.post(
    "",
    response_model=AiProviderOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_ai_provider(
    body: CreateAiProviderRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiProviderOut:
    """Create an AI provider configuration (admin only).

    ``api_key`` is stored encrypted (Fernet). It is never returned in any
    response. ``has_key`` on the response indicates whether a key was set.
    """
    ptype = _parse_provider_type(body.provider)
    encrypted_key: str | None = encrypt(body.api_key) if body.api_key else None

    p = AiProvider(
        provider=ptype,
        endpoint=body.endpoint,
        model=body.model,
        api_key_encrypted=encrypted_key,
        enabled=body.enabled,
    )
    db.add(p)
    await db.flush()
    return _to_out(p)


@router.get("/{provider_id}", response_model=AiProviderOut)
async def get_ai_provider(
    provider_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiProviderOut:
    """Get a single AI provider by ID (admin only)."""
    return _to_out(await _get_or_404(provider_id, db))


@router.patch("/{provider_id}", response_model=AiProviderOut)
async def patch_ai_provider(
    provider_id: int,
    body: PatchAiProviderRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiProviderOut:
    """Update an AI provider. Providing ``api_key`` rotates the stored key."""
    p = await _get_or_404(provider_id, db)

    if body.endpoint is not None:
        p.endpoint = body.endpoint
    if body.model is not None:
        p.model = body.model
    if body.api_key is not None:
        p.api_key_encrypted = encrypt(body.api_key)
    if body.enabled is not None:
        p.enabled = body.enabled

    await db.flush()
    return _to_out(p)


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_ai_provider(
    provider_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete an AI provider (admin only)."""
    p = await _get_or_404(provider_id, db)
    await db.delete(p)
    await db.flush()


@router.post("/{provider_id}/enable", response_model=AiProviderOut)
async def enable_ai_provider(
    provider_id: int,
    body: EnableRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiProviderOut:
    """Enable or disable an AI provider (admin only)."""
    p = await _get_or_404(provider_id, db)
    p.enabled = body.enabled
    await db.flush()
    return _to_out(p)


@router.post("/test", response_model=TestConnectionResponse)
async def test_ai_connection(
    body: TestConnectionRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> TestConnectionResponse:
    """Test an AI provider connection without persisting credentials.

    Sends a minimal ping prompt. The ``api_key`` in the request is used only
    for this call and is NOT stored. Returns ``ok=True`` on a successful
    response, ``ok=False`` with an ``error`` message otherwise.
    """
    from ..ai.client import _dispatch  # noqa: PLC0415

    ptype = _parse_provider_type(body.provider)

    # Build an ephemeral provider record (not persisted) for the dispatch call.
    ephemeral = AiProvider(
        provider=ptype,
        endpoint=body.endpoint,
        model=body.model,
        api_key_encrypted=None,
        enabled=True,
    )
    if body.api_key:
        # Encrypt ephemerally so _dispatch can decrypt it — never hits the DB.
        ephemeral.api_key_encrypted = encrypt(body.api_key)

    try:
        result = _dispatch(
            ephemeral,
            system="You are a helpful assistant.",
            user_msg="Reply with the single word 'ok'.",
            max_tokens=10,
        )
        if result is not None:
            return TestConnectionResponse(ok=True)
        return TestConnectionResponse(ok=False, error="No response from provider")
    except Exception as exc:
        return TestConnectionResponse(ok=False, error=str(exc))
