"""Manyfold instance admin endpoints (Part 1 of 3 — connector config + API).

Manyfold is a self-hosted 3D-model organizer with an OAuth2
(``client_credentials``) API. An admin registers one or more Manyfold
instances by domain, pasting an OAuth client ID + client secret; Part 2 (the
connector/worker/download) and Part 3 (frontend) build on this API to import a
model straight from a Manyfold URL.

  GET    /api/admin/manyfold                      → list instances (no secret)
  POST   /api/admin/manyfold                       → create an instance
  GET    /api/admin/manyfold/{id}                  → get one instance (no secret)
  PATCH  /api/admin/manyfold/{id}                  → update fields; rotates
                                                       the secret if provided
  DELETE /api/admin/manyfold/{id}                  → delete an instance
  POST   /api/admin/manyfold/{id}/test-connection   → fetch a token to verify
                                                       the stored credentials

Client secrets are Fernet-encrypted (``app.crypto``) and never returned by any
endpoint — responses expose ``has_secret: bool`` instead. All endpoints
require admin role, mirroring site_capabilities.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..crypto import decrypt, encrypt
from ..models.manyfold import ManyfoldInstance
from ..models.user import User
from ..storage.manyfold_client import (
    ManyfoldAuthError,
    ManyfoldConnectionError,
    ManyfoldScopeError,
    fetch_token,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/manyfold", tags=["admin-manyfold"])

DEFAULT_SCOPES = "public read"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ManyfoldInstanceOut(BaseModel):
    id: int
    base_url: str
    domain: str
    display_name: str | None
    client_id: str
    has_secret: bool  # whether client_secret_enc is set — secret itself never returned
    scopes: str
    enabled: bool
    last_connected_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": False}


class CreateManyfoldInstanceRequest(BaseModel):
    base_url: str
    display_name: str | None = None
    client_id: str
    client_secret: str  # plaintext; encrypted before storage; write-only
    scopes: str = DEFAULT_SCOPES
    enabled: bool = True
    notes: str | None = None


class PatchManyfoldInstanceRequest(BaseModel):
    base_url: str | None = None
    display_name: str | None = None
    client_id: str | None = None
    client_secret: str | None = None  # if provided, rotates the stored secret
    scopes: str | None = None
    enabled: bool | None = None
    notes: str | None = None


class TestConnectionResult(BaseModel):
    ok: bool
    scope: str | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_base_url(raw: str) -> tuple[str, str]:
    """Normalize a base_url and derive its domain.

    Strips a trailing slash (or trailing path slash), lowercases the host,
    and requires an http/https scheme. Returns ``(base_url, domain)`` where
    ``domain`` is the host only (no port), used as the unique match key.
    """
    raw = (raw or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="base_url is required.",
        )
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="base_url must start with http:// or https://.",
        )
    if not parsed.hostname:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="base_url must include a host.",
        )

    host = parsed.hostname.lower()
    port_part = f":{parsed.port}" if parsed.port else ""
    base_url = f"{parsed.scheme}://{host}{port_part}"
    path = parsed.path.rstrip("/")
    if path:
        base_url += path

    return base_url, host


async def _get_or_404(db: AsyncSession, instance_id: int) -> ManyfoldInstance:
    result = await db.execute(
        select(ManyfoldInstance).where(ManyfoldInstance.id == instance_id)
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manyfold instance not found.",
        )
    return inst


async def _domain_taken(
    db: AsyncSession, domain: str, *, exclude_id: int | None = None
) -> bool:
    q = select(ManyfoldInstance.id).where(ManyfoldInstance.domain == domain)
    if exclude_id is not None:
        q = q.where(ManyfoldInstance.id != exclude_id)
    result = await db.execute(q)
    return result.scalar_one_or_none() is not None


async def _to_out(db: AsyncSession, inst: ManyfoldInstance) -> ManyfoldInstanceOut:
    # Refresh to pick up server-generated values (e.g. updated_at's onupdate=
    # func.now() is expired after a flush that issued an UPDATE) — same
    # pattern as site_capabilities.py's _cap_out.
    await db.refresh(inst)
    return ManyfoldInstanceOut(
        id=inst.id,
        base_url=inst.base_url,
        domain=inst.domain,
        display_name=inst.display_name,
        client_id=inst.client_id,
        has_secret=bool(inst.client_secret_enc),
        scopes=inst.scopes,
        enabled=inst.enabled,
        last_connected_at=inst.last_connected_at,
        notes=inst.notes,
        created_at=inst.created_at,
        updated_at=inst.updated_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ManyfoldInstanceOut])
async def list_manyfold_instances(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ManyfoldInstanceOut]:
    """List all configured Manyfold instances (admin only). Secrets never returned."""
    result = await db.execute(
        select(ManyfoldInstance).order_by(ManyfoldInstance.id)
    )
    return [await _to_out(db, inst) for inst in result.scalars().all()]


@router.post("", response_model=ManyfoldInstanceOut, status_code=status.HTTP_201_CREATED)
async def create_manyfold_instance(
    body: CreateManyfoldInstanceRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManyfoldInstanceOut:
    """Register a Manyfold instance (admin only).

    ``client_secret`` is stored Fernet-encrypted and never returned. The
    domain is derived from ``base_url`` and must be unique — registering a
    second instance for the same host returns 409.
    """
    base_url, domain = _normalize_base_url(body.base_url)

    if await _domain_taken(db, domain):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A Manyfold instance for domain {domain!r} already exists.",
        )

    inst = ManyfoldInstance(
        base_url=base_url,
        domain=domain,
        display_name=body.display_name,
        client_id=body.client_id,
        client_secret_enc=encrypt(body.client_secret),
        scopes=body.scopes or DEFAULT_SCOPES,
        enabled=body.enabled,
        notes=body.notes,
    )
    db.add(inst)
    await db.flush()
    return await _to_out(db, inst)


@router.get("/{instance_id}", response_model=ManyfoldInstanceOut)
async def get_manyfold_instance(
    instance_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManyfoldInstanceOut:
    """Get a single Manyfold instance by ID (admin only)."""
    return await _to_out(db, await _get_or_404(db, instance_id))


@router.patch("/{instance_id}", response_model=ManyfoldInstanceOut)
async def patch_manyfold_instance(
    instance_id: int,
    body: PatchManyfoldInstanceRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManyfoldInstanceOut:
    """Update a Manyfold instance. Providing ``client_secret`` rotates it.

    Changing ``base_url`` re-derives and re-validates the unique domain.
    """
    inst = await _get_or_404(db, instance_id)

    if body.base_url is not None:
        base_url, domain = _normalize_base_url(body.base_url)
        if domain != inst.domain and await _domain_taken(
            db, domain, exclude_id=inst.id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A Manyfold instance for domain {domain!r} already exists.",
            )
        inst.base_url = base_url
        inst.domain = domain

    if body.display_name is not None:
        inst.display_name = body.display_name
    if body.client_id is not None:
        inst.client_id = body.client_id
    if body.client_secret is not None:
        inst.client_secret_enc = encrypt(body.client_secret)
    if body.scopes is not None:
        inst.scopes = body.scopes
    if body.enabled is not None:
        inst.enabled = body.enabled
    if body.notes is not None:
        inst.notes = body.notes

    await db.flush()
    return await _to_out(db, inst)


@router.delete(
    "/{instance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_manyfold_instance(
    instance_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a Manyfold instance (admin only)."""
    inst = await _get_or_404(db, instance_id)
    await db.delete(inst)
    await db.flush()


@router.post("/{instance_id}/test-connection", response_model=TestConnectionResult)
async def test_manyfold_connection(
    instance_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestConnectionResult:
    """Fetch an OAuth token to verify the stored credentials (admin only).

    On success, records ``last_connected_at`` and returns the granted scope.
    On failure, returns a structured ``ok=False`` result with a message
    describing the reason (bad credentials, scope not granted, or a
    connection/timeout error). Never echoes the secret.
    """
    inst = await _get_or_404(db, instance_id)

    if not inst.client_secret_enc:
        return TestConnectionResult(
            ok=False, message="No client secret configured — enter one and save first."
        )

    try:
        secret = decrypt(inst.client_secret_enc)
    except Exception:
        return TestConnectionResult(
            ok=False,
            message="Client secret decryption failed — re-enter the secret.",
        )

    _base_url = inst.base_url
    _client_id = inst.client_id
    _scopes = inst.scopes

    try:
        body = await asyncio.to_thread(
            fetch_token, _base_url, _client_id, secret, scopes=_scopes
        )
    except ManyfoldAuthError:
        return TestConnectionResult(
            ok=False, message="Invalid or missing client credentials (HTTP 401)."
        )
    except ManyfoldScopeError:
        return TestConnectionResult(
            ok=False, message="Requested scope was not granted (HTTP 403)."
        )
    except ManyfoldConnectionError as exc:
        return TestConnectionResult(ok=False, message=str(exc))

    granted_scope = str(body.get("scope") or "")
    inst.last_connected_at = datetime.now(UTC)
    await db.flush()
    return TestConnectionResult(ok=True, scope=granted_scope)
