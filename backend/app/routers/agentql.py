"""Scraper-backends admin endpoints (issue #23).

Provides admin-only endpoints for the pluggable fallback-scraper framework:

  AgentQL settings (existing, extended):
    GET  /api/admin/agentql                       → get AgentQL settings
    PUT  /api/admin/agentql                       → update AgentQL settings

  FlareSolverr settings (new):
    GET  /api/admin/scrapers/flaresolverr         → get FlareSolverr settings
    PUT  /api/admin/scrapers/flaresolverr         → update FlareSolverr settings

  Generic per-scraper settings (new):
    GET  /api/admin/scrapers/agentql              → get AgentQL generic knobs
                                                     (priority, timeout_s)
    PUT  /api/admin/scrapers/agentql              → update AgentQL generic knobs

  Test connection (new):
    POST /api/admin/scrapers/agentql/test-connection    → validate API key
    POST /api/admin/scrapers/flaresolverr/test-connection → ping solver

  Scraper usage (extended):
    GET    /api/admin/scraper-usage               → AgentQL billing window (compat)
    GET    /api/admin/scrapers/usage              → all-provider usage summary list
    DELETE /api/admin/scrapers/usage              → clear usage (?provider= optional)

Settings stored in the ``settings`` table (JSON rows, no migration needed):

  Existing AgentQL keys (kept for backward compatibility):
    agentql.enabled          → bool  (default false)
    agentql.api_key_enc      → Fernet-encrypted API key
    agentql.free_allowance   → int   (default 50)
    agentql.budget_mode      → "free_only" | "cap"
    agentql.monthly_cap_usd  → float | null
    agentql.per_call_usd     → float (default 0.02)

  New generic framework keys:
    scraper.agentql.priority     → int   (default 2; lower = tried first)
    scraper.agentql.timeout_s    → int   (default 120)
    scraper.flaresolverr.enabled → bool  (default false)
    scraper.flaresolverr.base_url → str  (e.g. "http://flaresolverr:8191")
    scraper.flaresolverr.timeout_s → int (default 60)
    scraper.flaresolverr.priority → int  (default 1)
    scraper.usage_retention_days → int   (default 30)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..crypto import encrypt
from ..models.scraper_usage import ScraperUsage
from ..models.setting import Setting
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(tags=["agentql"])

# Reset day of month for the budget window (1 = 1st of each month).
AGENTQL_RESET_DAY = 1

# ---------------------------------------------------------------------------
# Settings key constants
# ---------------------------------------------------------------------------

# AgentQL (existing keys — kept for backward compat)
_KEY_ENABLED = "agentql.enabled"
_KEY_API_KEY_ENC = "agentql.api_key_enc"
_KEY_FREE_ALLOWANCE = "agentql.free_allowance"
_KEY_BUDGET_MODE = "agentql.budget_mode"
_KEY_MONTHLY_CAP_USD = "agentql.monthly_cap_usd"
_KEY_PER_CALL_USD = "agentql.per_call_usd"

# Generic AgentQL framework keys (new)
_KEY_AQL_PRIORITY = "scraper.agentql.priority"
_KEY_AQL_TIMEOUT_S = "scraper.agentql.timeout_s"

# FlareSolverr settings (new)
_KEY_FS_ENABLED = "scraper.flaresolverr.enabled"
_KEY_FS_BASE_URL = "scraper.flaresolverr.base_url"
_KEY_FS_TIMEOUT_S = "scraper.flaresolverr.timeout_s"
_KEY_FS_PRIORITY = "scraper.flaresolverr.priority"

# Usage retention
_KEY_USAGE_RETENTION = "scraper.usage_retention_days"

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
    """Return the UTC start of the current billing window."""
    now = datetime.now(UTC)
    if now.day >= reset_day:
        return now.replace(
            day=reset_day, hour=0, minute=0, second=0, microsecond=0
        )
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
    has_key: bool
    free_allowance: int
    budget_mode: str
    monthly_cap_usd: float | None
    per_call_usd: float
    reset_day: int
    priority: int
    timeout_s: int


class AgentQLSettingsUpdateRequest(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    free_allowance: int | None = None
    budget_mode: str | None = None
    monthly_cap_usd: float | None = None
    per_call_usd: float | None = None
    priority: int | None = None
    timeout_s: int | None = None


class FlareSolverrSettingsOut(BaseModel):
    enabled: bool
    base_url: str
    timeout_s: int
    priority: int


class FlareSolverrSettingsUpdateRequest(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    timeout_s: int | None = None
    priority: int | None = None


class TestConnectionResult(BaseModel):
    ok: bool
    message: str


class ScraperUsageSummaryOut(BaseModel):
    """AgentQL-specific billing window summary (compat endpoint)."""
    calls: int
    est_cost_usd: float
    allowance: int
    mode: str
    cap: float | None
    resets_on: str
    per_call_usd: float


class ProviderUsageSummary(BaseModel):
    """Per-provider usage totals (all-providers endpoint)."""
    provider: str
    calls: int
    est_cost_usd: float


# ---------------------------------------------------------------------------
# AgentQL routes (existing, extended with priority/timeout_s)
# ---------------------------------------------------------------------------


@router.get("/api/admin/agentql", response_model=AgentQLSettingsOut)
async def get_agentql_settings(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentQLSettingsOut:
    """Get AgentQL fallback scraper settings (admin only)."""
    enabled = bool(await _get_setting(db, _KEY_ENABLED) or False)
    api_key_enc = await _get_setting(db, _KEY_API_KEY_ENC)
    has_key = bool(api_key_enc)
    free_allowance = int(await _get_setting(db, _KEY_FREE_ALLOWANCE) or 50)
    budget_mode = str(await _get_setting(db, _KEY_BUDGET_MODE) or "free_only")
    monthly_cap_usd_val = await _get_setting(db, _KEY_MONTHLY_CAP_USD)
    monthly_cap_usd = float(monthly_cap_usd_val) if monthly_cap_usd_val is not None else None
    per_call_usd = float(await _get_setting(db, _KEY_PER_CALL_USD) or 0.02)
    priority = int(await _get_setting(db, _KEY_AQL_PRIORITY) or 2)
    timeout_s = int(await _get_setting(db, _KEY_AQL_TIMEOUT_S) or 120)

    return AgentQLSettingsOut(
        enabled=enabled,
        has_key=has_key,
        free_allowance=free_allowance,
        budget_mode=budget_mode,
        monthly_cap_usd=monthly_cap_usd,
        per_call_usd=per_call_usd,
        reset_day=AGENTQL_RESET_DAY,
        priority=priority,
        timeout_s=timeout_s,
    )


@router.put("/api/admin/agentql", response_model=AgentQLSettingsOut)
async def update_agentql_settings(
    body: AgentQLSettingsUpdateRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentQLSettingsOut:
    """Update AgentQL fallback scraper settings (admin only)."""
    if body.enabled is not None:
        await _set_setting(db, _KEY_ENABLED, body.enabled)

    if body.api_key is not None:
        if body.api_key.strip():
            encrypted = encrypt(body.api_key.strip())
            await _set_setting(db, _KEY_API_KEY_ENC, encrypted)

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

    if body.priority is not None:
        if body.priority < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="priority must be >= 1.",
            )
        await _set_setting(db, _KEY_AQL_PRIORITY, body.priority)

    if body.timeout_s is not None:
        if body.timeout_s < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="timeout_s must be >= 1.",
            )
        await _set_setting(db, _KEY_AQL_TIMEOUT_S, body.timeout_s)

    return await get_agentql_settings(_admin, db)


# ---------------------------------------------------------------------------
# FlareSolverr routes (new)
# ---------------------------------------------------------------------------


@router.get("/api/admin/scrapers/flaresolverr", response_model=FlareSolverrSettingsOut)
async def get_flaresolverr_settings(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FlareSolverrSettingsOut:
    """Get FlareSolverr fallback scraper settings (admin only)."""
    enabled = bool(await _get_setting(db, _KEY_FS_ENABLED) or False)
    base_url = str(await _get_setting(db, _KEY_FS_BASE_URL) or "")
    timeout_s = int(await _get_setting(db, _KEY_FS_TIMEOUT_S) or 60)
    priority = int(await _get_setting(db, _KEY_FS_PRIORITY) or 1)
    return FlareSolverrSettingsOut(
        enabled=enabled,
        base_url=base_url,
        timeout_s=timeout_s,
        priority=priority,
    )


@router.put("/api/admin/scrapers/flaresolverr", response_model=FlareSolverrSettingsOut)
async def update_flaresolverr_settings(
    body: FlareSolverrSettingsUpdateRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FlareSolverrSettingsOut:
    """Update FlareSolverr fallback scraper settings (admin only)."""
    if body.enabled is not None:
        await _set_setting(db, _KEY_FS_ENABLED, body.enabled)

    if body.base_url is not None:
        await _set_setting(db, _KEY_FS_BASE_URL, body.base_url.strip())

    if body.timeout_s is not None:
        if body.timeout_s < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="timeout_s must be >= 1.",
            )
        await _set_setting(db, _KEY_FS_TIMEOUT_S, body.timeout_s)

    if body.priority is not None:
        if body.priority < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="priority must be >= 1.",
            )
        await _set_setting(db, _KEY_FS_PRIORITY, body.priority)

    return await get_flaresolverr_settings(_admin, db)


# ---------------------------------------------------------------------------
# Test-connection routes (new)
# ---------------------------------------------------------------------------


@router.post(
    "/api/admin/scrapers/flaresolverr/test-connection",
    response_model=TestConnectionResult,
)
async def test_flaresolverr_connection(
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestConnectionResult:
    """Ping FlareSolverr's root endpoint to verify it is reachable (admin only).

    Makes a real HTTP GET to ``<base_url>/`` and checks for the expected JSON
    health response.  Does NOT make a scrape call, so no usage is recorded.
    """
    import asyncio  # noqa: PLC0415

    base_url = str(await _get_setting(db, _KEY_FS_BASE_URL) or "").strip()
    if not base_url:
        return TestConnectionResult(
            ok=False,
            message="FlareSolverr base URL not configured. Set it above.",
        )

    try:
        from ..storage.flaresolverr_client import flaresolverr_health  # noqa: PLC0415

        _b = base_url
        data: dict = await asyncio.get_event_loop().run_in_executor(  # type: ignore[type-arg]
            None, lambda: flaresolverr_health(_b)
        )
        msg = str(data.get("msg", "OK"))
        version = str(data.get("version", ""))
        full = f"{msg} (version {version})" if version else msg
        return TestConnectionResult(ok=True, message=full)
    except Exception as exc:
        return TestConnectionResult(ok=False, message=f"Connection failed: {exc}")


@router.post(
    "/api/admin/scrapers/agentql/test-connection",
    response_model=TestConnectionResult,
)
async def test_agentql_connection(
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestConnectionResult:
    """Validate the AgentQL API key with a cheap probe call (admin only).

    Makes a real AgentQL API request to verify the key is accepted.
    This counts as one call against your AgentQL quota.
    """
    import asyncio  # noqa: PLC0415

    from ..crypto import InvalidToken, decrypt  # noqa: PLC0415

    api_key_enc = await _get_setting(db, _KEY_API_KEY_ENC)
    if not api_key_enc:
        return TestConnectionResult(
            ok=False, message="AgentQL API key not configured. Paste your key above."
        )

    try:
        api_key = decrypt(str(api_key_enc))
    except InvalidToken:
        return TestConnectionResult(
            ok=False,
            message="API key decryption failed — re-enter the key in settings.",
        )

    try:
        from ..storage.agentql_client import agentql_scrape  # noqa: PLC0415

        timeout_s = int(await _get_setting(db, _KEY_AQL_TIMEOUT_S) or 120)
        _key = api_key
        _timeout = timeout_s
        sr = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: agentql_scrape(
                "https://example.com", _key,
                timeout=_timeout,
                proxy_enabled=False,  # cheap — no proxy for the test call
            ),
        )
        if sr.blocked and sr.note and "authentication" in sr.note.lower():
            return TestConnectionResult(ok=False, message=sr.note)
        if sr.blocked and sr.note and "quota" in sr.note.lower():
            return TestConnectionResult(ok=False, message=sr.note)
        # Any non-auth-failure is counted as "key accepted" (even if the page
        # was blocked by Cloudflare — the key itself is valid).
        return TestConnectionResult(ok=True, message="AgentQL API key accepted.")
    except Exception as exc:
        return TestConnectionResult(ok=False, message=f"Test failed: {exc}")


# ---------------------------------------------------------------------------
# Scraper usage routes (existing + extended)
# ---------------------------------------------------------------------------


@router.get("/api/admin/scraper-usage", response_model=ScraperUsageSummaryOut)
async def get_scraper_usage(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScraperUsageSummaryOut:
    """Return AgentQL usage for the current billing window (admin only, compat).

    Note: This is our local call count for AgentQL only.  For all-provider
    usage use GET /api/admin/scrapers/usage.
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

    free_allowance = int(await _get_setting(db, _KEY_FREE_ALLOWANCE) or 50)
    budget_mode = str(await _get_setting(db, _KEY_BUDGET_MODE) or "free_only")
    monthly_cap_usd_val = await _get_setting(db, _KEY_MONTHLY_CAP_USD)
    monthly_cap_usd = float(monthly_cap_usd_val) if monthly_cap_usd_val is not None else None
    per_call_usd = float(await _get_setting(db, _KEY_PER_CALL_USD) or 0.02)

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


@router.get(
    "/api/admin/scrapers/usage",
    response_model=list[ProviderUsageSummary],
)
async def get_all_scraper_usage(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: str | None = Query(default=None, description="Filter by provider name"),
) -> list[ProviderUsageSummary]:
    """Return per-provider scraper usage totals (all-time, admin only).

    Optionally filter with ``?provider=agentql`` or ``?provider=flaresolverr``.
    """
    q = select(
        ScraperUsage.provider,
        func.count(ScraperUsage.id),
        func.coalesce(func.sum(ScraperUsage.est_cost_usd), 0.0),
    ).group_by(ScraperUsage.provider)

    if provider:
        q = q.where(ScraperUsage.provider == provider)

    result = await db.execute(q)
    return [
        ProviderUsageSummary(
            provider=row[0],
            calls=int(row[1]),
            est_cost_usd=round(float(row[2]), 6),
        )
        for row in result.all()
    ]


@router.delete(
    "/api/admin/scrapers/usage",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def clear_scraper_usage(
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: str | None = Query(
        default=None,
        description="Provider to clear (agentql, flaresolverr). Omit to clear all.",
    ),
) -> None:
    """Clear scraper usage rows (admin only).

    Without ``?provider=``: clears ALL providers' usage history.
    With ``?provider=agentql`` or ``?provider=flaresolverr``: clears only that
    provider's rows.
    """
    q = delete(ScraperUsage)
    if provider:
        q = q.where(ScraperUsage.provider == provider)
    await db.execute(q)
    await db.commit()
    log.info(
        "clear_scraper_usage: cleared usage rows (provider=%r)", provider or "ALL"
    )
