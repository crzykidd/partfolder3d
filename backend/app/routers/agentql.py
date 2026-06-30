"""AgentQL fallback scraper admin endpoints (Phase 18).

Provides admin-only endpoints for:
  GET  /api/admin/agentql         → get AgentQL settings (key write-only)
  PUT  /api/admin/agentql         → update AgentQL settings
  GET  /api/admin/scraper-usage   → current billing window usage summary

Settings are stored in the instance `settings` table:
  agentql.enabled          → bool (default false)
  agentql.api_key_enc      → Fernet-encrypted API key string
  agentql.free_allowance   → int (default 50)
  agentql.budget_mode      → "free_only" | "cap" (default "free_only")
  agentql.monthly_cap_usd  → float | null
  agentql.per_call_usd     → float (default 0.02)

The budget window resets on AGENTQL_RESET_DAY (the 1st of each month).
This is a config constant, not yet exposed as a UI field.

Key is never returned in any response; ``has_key`` indicates whether a key is set.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..crypto import encrypt
from ..models.scraper_usage import ScraperUsage
from ..models.setting import Setting
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(tags=["agentql"])

# Reset day of month for the budget window (1 = 1st of each month).
# Not exposed in the UI yet; trivially editable here.
AGENTQL_RESET_DAY = 1

# Setting keys in the instance settings table
_KEY_ENABLED = "agentql.enabled"
_KEY_API_KEY_ENC = "agentql.api_key_enc"
_KEY_FREE_ALLOWANCE = "agentql.free_allowance"
_KEY_BUDGET_MODE = "agentql.budget_mode"
_KEY_MONTHLY_CAP_USD = "agentql.monthly_cap_usd"
_KEY_PER_CALL_USD = "agentql.per_call_usd"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_setting(db: AsyncSession, key: str) -> object | None:
    """Load a single setting by key; returns parsed JSON value or None."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return json.loads(row.value) if row else None


async def _set_setting(db: AsyncSession, key: str, value: object) -> None:
    """Upsert a setting by key."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    json_val = json.dumps(value)
    if row:
        row.value = json_val
    else:
        row = Setting(key=key, value=json_val)
        db.add(row)
    await db.flush()


def _window_start(reset_day: int = AGENTQL_RESET_DAY) -> datetime:
    """Return the UTC start of the current budget window.

    The window starts on ``reset_day`` of the current month if today >= reset_day,
    otherwise on ``reset_day`` of the previous month.
    """
    now = datetime.now(UTC)
    if now.day >= reset_day:
        return now.replace(
            day=reset_day, hour=0, minute=0, second=0, microsecond=0
        )
    # Previous month
    if now.month == 1:
        return now.replace(
            year=now.year - 1, month=12, day=reset_day,
            hour=0, minute=0, second=0, microsecond=0,
        )
    return now.replace(
        month=now.month - 1, day=reset_day,
        hour=0, minute=0, second=0, microsecond=0,
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AgentQLSettingsOut(BaseModel):
    enabled: bool
    has_key: bool  # True when an encrypted key is stored; plaintext never returned
    free_allowance: int
    budget_mode: str  # "free_only" | "cap"
    monthly_cap_usd: float | None
    per_call_usd: float
    reset_day: int


class AgentQLSettingsUpdateRequest(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None  # plaintext; encrypted before storage; write-only
    free_allowance: int | None = None
    budget_mode: str | None = None
    monthly_cap_usd: float | None = None
    per_call_usd: float | None = None


class ScraperUsageSummaryOut(BaseModel):
    calls: int
    est_cost_usd: float
    allowance: int
    mode: str          # "free_only" | "cap"
    cap: float | None  # monthly_cap_usd (None when mode=free_only or not set)
    resets_on: str     # ISO date string of the next reset (first of next month)
    per_call_usd: float


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/admin/agentql", response_model=AgentQLSettingsOut)
async def get_agentql_settings(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentQLSettingsOut:
    """Get AgentQL fallback scraper settings (admin only).

    The API key is never returned; ``has_key`` indicates whether a key is set.
    """
    enabled = bool(await _get_setting(db, _KEY_ENABLED) or False)
    api_key_enc = await _get_setting(db, _KEY_API_KEY_ENC)
    has_key = bool(api_key_enc)
    free_allowance = int(await _get_setting(db, _KEY_FREE_ALLOWANCE) or 50)
    budget_mode = str(await _get_setting(db, _KEY_BUDGET_MODE) or "free_only")
    monthly_cap_usd_val = await _get_setting(db, _KEY_MONTHLY_CAP_USD)
    monthly_cap_usd = float(monthly_cap_usd_val) if monthly_cap_usd_val is not None else None
    per_call_usd = float(await _get_setting(db, _KEY_PER_CALL_USD) or 0.02)

    return AgentQLSettingsOut(
        enabled=enabled,
        has_key=has_key,
        free_allowance=free_allowance,
        budget_mode=budget_mode,
        monthly_cap_usd=monthly_cap_usd,
        per_call_usd=per_call_usd,
        reset_day=AGENTQL_RESET_DAY,
    )


@router.put("/api/admin/agentql", response_model=AgentQLSettingsOut)
async def update_agentql_settings(
    body: AgentQLSettingsUpdateRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentQLSettingsOut:
    """Update AgentQL fallback scraper settings (admin only).

    Providing ``api_key`` (plaintext) rotates the encrypted stored key.
    The key is never returned in any response.

    ``budget_mode`` must be one of: ``free_only``, ``cap``.
    ``per_call_usd`` defaults to $0.02 (AgentQL Starter rate at time of writing).
    """
    if body.enabled is not None:
        await _set_setting(db, _KEY_ENABLED, body.enabled)

    if body.api_key is not None:
        if body.api_key.strip():
            encrypted = encrypt(body.api_key.strip())
            await _set_setting(db, _KEY_API_KEY_ENC, encrypted)
        # Empty string → silently ignore (don't wipe the key)

    if body.free_allowance is not None:
        if body.free_allowance < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="free_allowance must be >= 0.",
            )
        await _set_setting(db, _KEY_FREE_ALLOWANCE, body.free_allowance)

    if body.budget_mode is not None:
        if body.budget_mode not in ("free_only", "cap"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="budget_mode must be 'free_only' or 'cap'.",
            )
        await _set_setting(db, _KEY_BUDGET_MODE, body.budget_mode)

    if body.monthly_cap_usd is not None:
        await _set_setting(db, _KEY_MONTHLY_CAP_USD, body.monthly_cap_usd)

    if body.per_call_usd is not None:
        if body.per_call_usd < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="per_call_usd must be >= 0.",
            )
        await _set_setting(db, _KEY_PER_CALL_USD, body.per_call_usd)

    # Return current state
    return await get_agentql_settings(_admin, db)


@router.get("/api/admin/scraper-usage", response_model=ScraperUsageSummaryOut)
async def get_scraper_usage(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScraperUsageSummaryOut:
    """Return AgentQL usage for the current billing window (admin only).

    Window = from the most recent AGENTQL_RESET_DAY (1st) at 00:00 UTC → now.

    Note: This is our local call count.  The AgentQL dashboard is authoritative
    for actual billing.  Our count ≈ real usage when this key is the sole consumer.
    """
    ws = _window_start()
    result = await db.execute(
        select(
            func.count(ScraperUsage.id),
            func.coalesce(func.sum(ScraperUsage.est_cost_usd), 0.0),
        ).where(
            ScraperUsage.created_at >= ws,
            ScraperUsage.provider == "agentql",
        )
    )
    calls_raw, cost_raw = result.one()
    calls = int(calls_raw)
    est_cost = round(float(cost_raw), 6)

    # Load settings for the summary
    free_allowance = int(await _get_setting(db, _KEY_FREE_ALLOWANCE) or 50)
    budget_mode = str(await _get_setting(db, _KEY_BUDGET_MODE) or "free_only")
    monthly_cap_usd_val = await _get_setting(db, _KEY_MONTHLY_CAP_USD)
    monthly_cap_usd = float(monthly_cap_usd_val) if monthly_cap_usd_val is not None else None
    per_call_usd = float(await _get_setting(db, _KEY_PER_CALL_USD) or 0.02)

    # Next reset = 1st of next month
    now = datetime.now(UTC)
    if now.month == 12:
        next_reset = now.replace(
            year=now.year + 1, month=1, day=AGENTQL_RESET_DAY,
            hour=0, minute=0, second=0, microsecond=0,
        )
    else:
        next_reset = now.replace(
            month=now.month + 1, day=AGENTQL_RESET_DAY,
            hour=0, minute=0, second=0, microsecond=0,
        )

    return ScraperUsageSummaryOut(
        calls=calls,
        est_cost_usd=est_cost,
        allowance=free_allowance,
        mode=budget_mode,
        cap=monthly_cap_usd,
        resets_on=next_reset.date().isoformat(),
        per_call_usd=per_call_usd,
    )
