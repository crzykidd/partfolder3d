"""AI usage summary endpoint — Phase 13.

GET /api/ai-usage/summary (admin only):
  Returns per-window (24h / 7d / 30d) call counts, token totals, and
  estimated cost in USD, plus a provider/model breakdown for the 30d window.

All token-window aggregations run as efficient grouped SQL queries over the
created_at index.  Estimated costs are derived from the local pricing table;
they are labelled as estimates (rates may drift).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.pricing import estimate_cost
from ..auth.deps import get_current_user, get_db
from ..models.ai_usage import AiUsage
from ..models.user import User, UserRole

log = logging.getLogger(__name__)

router = APIRouter(tags=["ai-usage"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class WindowSummary(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    """None when one or more contributing models have an unknown rate (shown as '—' in UI)."""


class ProviderBreakdown(BaseModel):
    provider: str
    model: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    """None when the model's rate is unknown ('—' in UI)."""


class AiUsageSummaryOut(BaseModel):
    last_24h: WindowSummary
    last_7d: WindowSummary
    last_30d: WindowSummary
    breakdown: list[ProviderBreakdown]
    """Provider/model breakdown for the 30-day window, descending by call count."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_window_summary(
    calls: int,
    inp: int,
    out: int,
    total: int,
    estimated_cost_usd: float | None,
) -> WindowSummary:
    return WindowSummary(
        calls=calls,
        input_tokens=inp,
        output_tokens=out,
        total_tokens=total,
        estimated_cost_usd=estimated_cost_usd,
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/api/ai-usage/summary", response_model=AiUsageSummaryOut)
async def get_ai_usage_summary(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiUsageSummaryOut:
    """Return AI usage totals for 24h / 7d / 30d windows (admin only).

    Includes per-window token counts and estimated cost in USD (derived from the
    local pricing table).  Cost is ``null`` when any contributing model has an
    unknown rate — individual breakdown rows always show the per-row cost.
    """
    if user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin only."
        )

    now = datetime.now(UTC)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    # ------------------------------------------------------------------
    # Breakdown by provider + model for the 30d window (used for all
    # per-window aggregation too — cheaper than running separate queries).
    # ------------------------------------------------------------------
    breakdown_result = await db.execute(
        select(
            AiUsage.provider,
            AiUsage.model,
            func.count(AiUsage.id),
            func.coalesce(func.sum(AiUsage.input_tokens), 0),
            func.coalesce(func.sum(AiUsage.output_tokens), 0),
            func.coalesce(func.sum(AiUsage.total_tokens), 0),
            func.min(AiUsage.created_at),  # earliest in window (for bucket filtering)
        )
        .where(AiUsage.created_at >= cutoff_30d)
        .group_by(AiUsage.provider, AiUsage.model)
        .order_by(func.count(AiUsage.id).desc())
    )
    breakdown_rows = breakdown_result.all()

    # Build a ProviderBreakdown per group (30d window)
    breakdown: list[ProviderBreakdown] = []
    for prov, mod, calls, inp, out, total, _min_at in breakdown_rows:
        cost = estimate_cost(prov, mod, int(inp), int(out))
        breakdown.append(
            ProviderBreakdown(
                provider=prov,
                model=mod,
                calls=int(calls),
                input_tokens=int(inp),
                output_tokens=int(out),
                total_tokens=int(total),
                estimated_cost_usd=cost,
            )
        )

    # ------------------------------------------------------------------
    # Per-window aggregations via efficient grouped SQL on the index.
    # Run all three as separate queries (simple, index-covered).
    # ------------------------------------------------------------------
    async def _window(cutoff: datetime) -> WindowSummary:
        row = await db.execute(
            select(
                func.count(AiUsage.id),
                func.coalesce(func.sum(AiUsage.input_tokens), 0),
                func.coalesce(func.sum(AiUsage.output_tokens), 0),
                func.coalesce(func.sum(AiUsage.total_tokens), 0),
            ).where(AiUsage.created_at >= cutoff)
        )
        calls, inp, out, total = row.one()
        calls = int(calls)
        inp = int(inp)
        out = int(out)
        total = int(total)

        # To compute estimated cost: sum per-row costs for rows in this window,
        # using the breakdown data from the 30d query (already fetched).
        # For 24h/7d we need more granular data — run a provider-level query.
        cost_result = await db.execute(
            select(
                AiUsage.provider,
                AiUsage.model,
                func.coalesce(func.sum(AiUsage.input_tokens), 0),
                func.coalesce(func.sum(AiUsage.output_tokens), 0),
            )
            .where(AiUsage.created_at >= cutoff)
            .group_by(AiUsage.provider, AiUsage.model)
        )
        total_cost: float | None = 0.0
        for prov, mod, w_inp, w_out in cost_result.all():
            c = estimate_cost(prov, mod, int(w_inp), int(w_out))
            if c is None:
                # Unknown rate — mark entire window cost as unknown
                total_cost = None
                break
            if total_cost is not None:
                total_cost += c

        if total_cost is not None:
            total_cost = round(total_cost, 8)

        return _make_window_summary(calls, inp, out, total, total_cost)

    last_24h = await _window(cutoff_24h)
    last_7d = await _window(cutoff_7d)
    last_30d = await _window(cutoff_30d)

    return AiUsageSummaryOut(
        last_24h=last_24h,
        last_7d=last_7d,
        last_30d=last_30d,
        breakdown=breakdown,
    )
