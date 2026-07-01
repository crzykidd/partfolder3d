"""Phase 13: AI usage tracking tests.

Coverage:
  1. AiCallResult normalization — str → AiCallResult(0, 0) in _dispatch.
  2. Real-caller token capture — _dispatch returns AiCallResult with tokens.
  3. suggest_tags populates input_tokens / output_tokens from _dispatch result.
  4. cleanup_description populates token counts.
  5. summarize_scrape populates token counts.
  6. AI action endpoint writes AiUsage row with correct tokens (mocked).
  7. AI action endpoint with no provider → no AiUsage row written.
  8. Recording failure is swallowed — AI feature still returns 200.
  9. Summary endpoint returns correct windowed totals.
  10. Summary endpoint: known Claude model → estimated_cost_usd correct.
  11. Summary endpoint: unknown model → estimated_cost_usd is None per row.
  12. Summary endpoint: non-admin forbidden (403).
  13. Pricing: estimate_cost for known Claude model.
  14. Pricing: Ollama always $0.
  15. Pricing: unknown / OpenAI model → None.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_provider import AiProvider, AiProviderType
from app.models.ai_usage import AiUsage

# ---------------------------------------------------------------------------
# Auth helper (shared)
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> str:
    """Bootstrap instance and return CSRF token for the admin session."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@test.com",
            "admin_name": "Admin",
            "admin_password": "adminpassword1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "adminpassword1"},
    )
    assert resp.status_code == 200
    return client.cookies.get("pf3d_csrf", "")


# ---------------------------------------------------------------------------
# 1. AiCallResult normalization in _dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_normalizes_str_to_ai_call_result() -> None:
    """Patching _anthropic_caller to return str → _dispatch yields AiCallResult(0, 0)."""
    from app.ai.client import AiCallResult, _dispatch  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()
    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    with patch("app.ai.client._anthropic_caller", lambda *a: "hello world"):
        result = _dispatch(provider, "sys", "usr")

    assert isinstance(result, AiCallResult)
    assert result.text == "hello world"
    assert result.input_tokens == 0
    assert result.output_tokens == 0


@pytest.mark.asyncio
async def test_dispatch_normalizes_none_caller_result() -> None:
    """Patching caller to return None → _dispatch returns None."""
    from app.ai.client import _dispatch  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()
    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    with patch("app.ai.client._anthropic_caller", lambda *a: None):
        result = _dispatch(provider, "sys", "usr")

    assert result is None


@pytest.mark.asyncio
async def test_dispatch_passes_through_ai_call_result() -> None:
    """Caller returning AiCallResult with tokens → passes through unchanged."""
    from app.ai.client import AiCallResult, _dispatch  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()
    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    expected = AiCallResult(text="response", input_tokens=100, output_tokens=50)

    with patch("app.ai.client._anthropic_caller", lambda *a: expected):
        result = _dispatch(provider, "sys", "usr")

    assert result is expected
    assert result.input_tokens == 100
    assert result.output_tokens == 50


# ---------------------------------------------------------------------------
# 2–5. Token propagation through public functions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_tags_propagates_tokens() -> None:
    """suggest_tags carries input/output tokens from the mocked caller."""
    from app.ai.client import AiCallResult, suggest_tags  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()
    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    mock_json = json.dumps({"canonical": ["fdm"], "new_suggestions": []})
    mock_result = AiCallResult(text=mock_json, input_tokens=200, output_tokens=30)

    with patch("app.ai.client._anthropic_caller", lambda *a: mock_result):
        result = suggest_tags(
            provider=provider,
            title="Test",
            description=None,
            scraped_text=None,
            filenames=[],
            existing_tags=["fdm"],
        )

    assert result.input_tokens == 200
    assert result.output_tokens == 30
    assert result.error is None


@pytest.mark.asyncio
async def test_cleanup_description_propagates_tokens() -> None:
    from app.ai.client import AiCallResult, cleanup_description  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()
    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    mock_result = AiCallResult(text="Clean text.", input_tokens=150, output_tokens=20)

    with patch("app.ai.client._anthropic_caller", lambda *a: mock_result):
        result = cleanup_description(provider=provider, description="bad text", title="T")

    assert result.input_tokens == 150
    assert result.output_tokens == 20
    assert result.error is None


@pytest.mark.asyncio
async def test_summarize_scrape_propagates_tokens() -> None:
    from app.ai.client import AiCallResult, summarize_scrape  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()
    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    mock_result = AiCallResult(text="A nice summary.", input_tokens=300, output_tokens=40)

    with patch("app.ai.client._anthropic_caller", lambda *a: mock_result):
        result = summarize_scrape(
            provider=provider, scraped_text="lots of text", title="T"
        )

    assert result.input_tokens == 300
    assert result.output_tokens == 40
    assert result.error is None


# ---------------------------------------------------------------------------
# 6. Action endpoint writes AiUsage row with correct tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_action_records_usage_row(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """suggest-tags with a mocked provider writes an AiUsage row with token counts."""
    from app.ai.client import AiCallResult  # noqa: PLC0415
    from app.crypto import encrypt  # noqa: PLC0415
    from app.models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionStatus,
        ImportSourceType,
    )
    from app.models.user import User  # noqa: PLC0415

    csrf = await _setup_and_login(client)

    user_res = await db_session.execute(select(User).limit(1))
    admin = user_res.scalar_one()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    db_session.add(provider)

    session = ImportSession(
        status=ImportSessionStatus.pending_wizard,
        source_type=ImportSourceType.upload,
        confirmed_title="Test Item",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    mock_json = json.dumps({"canonical": [], "new_suggestions": ["cool-tag"]})
    mock_result = AiCallResult(text=mock_json, input_tokens=111, output_tokens=22)

    with patch("app.ai.client._anthropic_caller", lambda *a: mock_result):
        resp = await client.post(
            f"/api/import-sessions/{session.id}/ai/suggest-tags",
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is True

    # Verify AiUsage row was written
    usage_result = await db_session.execute(
        select(AiUsage).where(AiUsage.action == "suggest_tags")
    )
    rows = usage_result.scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "claude"
    assert row.model == "claude-opus-4-8"
    assert row.input_tokens == 111
    assert row.output_tokens == 22
    assert row.total_tokens == 133
    assert row.success is True
    assert row.user_id == admin.id


# ---------------------------------------------------------------------------
# 7. No provider → no AiUsage row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_provider_writes_no_usage_row(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """suggest-tags with no provider writes no AiUsage row."""
    from app.models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionStatus,
        ImportSourceType,
    )
    from app.models.user import User  # noqa: PLC0415

    csrf = await _setup_and_login(client)

    user_res = await db_session.execute(select(User).limit(1))
    admin = user_res.scalar_one()

    session = ImportSession(
        status=ImportSessionStatus.pending_wizard,
        source_type=ImportSourceType.upload,
        confirmed_title="Test Item",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{session.id}/ai/suggest-tags",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["provider_available"] is False

    usage_result = await db_session.execute(select(AiUsage))
    assert len(usage_result.scalars().all()) == 0


# ---------------------------------------------------------------------------
# 8. Recording failure swallowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_recording_failure_is_swallowed(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """If AiUsage.flush raises, the AI endpoint still returns 200."""
    from app.ai.client import AiCallResult  # noqa: PLC0415
    from app.crypto import encrypt  # noqa: PLC0415
    from app.models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionStatus,
        ImportSourceType,
    )
    from app.models.user import User  # noqa: PLC0415
    from app.routers import ai_actions  # noqa: PLC0415

    csrf = await _setup_and_login(client)

    user_res = await db_session.execute(select(User).limit(1))
    admin = user_res.scalar_one()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    db_session.add(provider)

    session = ImportSession(
        status=ImportSessionStatus.pending_wizard,
        source_type=ImportSourceType.upload,
        confirmed_title="Test Item",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    mock_json = json.dumps({"canonical": [], "new_suggestions": []})
    mock_result = AiCallResult(text=mock_json, input_tokens=10, output_tokens=5)

    async def _raise(*a, **kw):
        raise RuntimeError("DB write error simulated")

    with (
        patch("app.ai.client._anthropic_caller", lambda *a: mock_result),
        patch.object(ai_actions, "_record_usage", _raise),
    ):
        resp = await client.post(
            f"/api/import-sessions/{session.id}/ai/suggest-tags",
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    assert resp.json()["provider_available"] is True


# ---------------------------------------------------------------------------
# 9. Summary endpoint — windowed totals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_endpoint_windowed_totals(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Summary endpoint returns correct totals across time windows."""
    csrf = await _setup_and_login(client)

    now = datetime.now(UTC)

    # Row 1: within 24h (counts in 24h / 7d / 30d)
    r1 = AiUsage(
        created_at=now - timedelta(hours=1),
        provider="claude",
        model="claude-opus-4-8",
        action="suggest_tags",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        success=True,
    )
    # Row 2: within 7d but not 24h (counts in 7d / 30d only)
    r2 = AiUsage(
        created_at=now - timedelta(days=3),
        provider="claude",
        model="claude-opus-4-8",
        action="cleanup_description",
        input_tokens=200,
        output_tokens=80,
        total_tokens=280,
        success=True,
    )
    # Row 3: within 30d but not 7d (counts in 30d only)
    r3 = AiUsage(
        created_at=now - timedelta(days=15),
        provider="ollama",
        model="llama3",
        action="summarize",
        input_tokens=300,
        output_tokens=100,
        total_tokens=400,
        success=True,
    )
    # Row 4: older than 30d (counts in no window)
    r4 = AiUsage(
        created_at=now - timedelta(days=45),
        provider="claude",
        model="claude-opus-4-8",
        action="suggest_tags",
        input_tokens=999,
        output_tokens=999,
        total_tokens=1998,
        success=True,
    )
    for row in (r1, r2, r3, r4):
        db_session.add(row)
    await db_session.flush()

    resp = await client.get("/api/ai-usage/summary", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    data = resp.json()

    h24 = data["last_24h"]
    assert h24["calls"] == 1
    assert h24["input_tokens"] == 100
    assert h24["output_tokens"] == 50
    assert h24["total_tokens"] == 150

    d7 = data["last_7d"]
    assert d7["calls"] == 2
    assert d7["input_tokens"] == 300
    assert d7["output_tokens"] == 130

    d30 = data["last_30d"]
    assert d30["calls"] == 3
    assert d30["input_tokens"] == 600
    assert d30["output_tokens"] == 230


# ---------------------------------------------------------------------------
# 10. Summary endpoint — estimated cost for known Claude model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_endpoint_cost_known_model(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Known Claude model → estimated_cost_usd is calculated correctly."""
    csrf = await _setup_and_login(client)

    now = datetime.now(UTC)
    # claude-opus-4-8: input=$5/MTok, output=$25/MTok
    # 1,000,000 input tokens → $5.00; 200,000 output tokens → $5.00 → total $10.00
    r = AiUsage(
        created_at=now - timedelta(hours=1),
        provider="claude",
        model="claude-opus-4-8",
        action="suggest_tags",
        input_tokens=1_000_000,
        output_tokens=200_000,
        total_tokens=1_200_000,
        success=True,
    )
    db_session.add(r)
    await db_session.flush()

    resp = await client.get("/api/ai-usage/summary", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    data = resp.json()

    cost = data["last_24h"]["estimated_cost_usd"]
    assert cost is not None
    assert abs(cost - 10.0) < 0.001

    # Check breakdown row too
    bd = data["breakdown"]
    assert len(bd) >= 1
    assert bd[0]["estimated_cost_usd"] is not None


# ---------------------------------------------------------------------------
# 11. Summary endpoint — unknown model → estimated_cost_usd is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_endpoint_cost_unknown_model(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Unknown / OpenAI model → estimated_cost_usd is None (shown as '—' in UI)."""
    csrf = await _setup_and_login(client)

    now = datetime.now(UTC)
    r = AiUsage(
        created_at=now - timedelta(hours=1),
        provider="openai",
        model="gpt-4o-mini",
        action="suggest_tags",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        success=True,
    )
    db_session.add(r)
    await db_session.flush()

    resp = await client.get("/api/ai-usage/summary", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_24h"]["estimated_cost_usd"] is None

    bd = data["breakdown"]
    openai_row = next((b for b in bd if b["provider"] == "openai"), None)
    assert openai_row is not None
    assert openai_row["estimated_cost_usd"] is None


# ---------------------------------------------------------------------------
# 12. Summary endpoint — non-admin is forbidden
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_endpoint_non_admin_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    from app.auth.password import hash_password  # noqa: PLC0415
    from app.models.user import User, UserRole  # noqa: PLC0415

    await _setup_and_login(client)

    regular = User(
        email="user@test.com",
        name="Regular User",
        role=UserRole.user,
        password_hash=hash_password("userpass1"),
    )
    db_session.add(regular)
    await db_session.flush()

    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "user@test.com", "password": "userpass1"},
    )
    assert login_resp.status_code == 200
    user_csrf = client.cookies.get("pf3d_csrf", "")

    resp = await client.get("/api/ai-usage/summary", headers={"x-csrf-token": user_csrf})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 13–15. Pricing unit tests
# ---------------------------------------------------------------------------


def test_pricing_known_claude_model() -> None:
    """claude-opus-4-8: $5/MTok in, $25/MTok out."""
    from app.ai.pricing import estimate_cost  # noqa: PLC0415

    cost = estimate_cost("claude", "claude-opus-4-8", 1_000_000, 1_000_000)
    assert cost is not None
    assert abs(cost - 30.0) < 0.001  # 5+25


def test_pricing_ollama_is_zero() -> None:
    """Ollama always returns $0 regardless of model."""
    from app.ai.pricing import estimate_cost  # noqa: PLC0415

    cost = estimate_cost("ollama", "llama3", 1_000_000, 1_000_000)
    assert cost == 0.0


def test_pricing_openai_unknown_is_none() -> None:
    """OpenAI model not in pricing table → None."""
    from app.ai.pricing import estimate_cost  # noqa: PLC0415

    cost = estimate_cost("openai", "gpt-4o-mini", 100, 50)
    assert cost is None


def test_pricing_claude_opus_wildcard_fallback() -> None:
    """Any claude-opus-* model not explicitly listed → uses $5/$25 default."""
    from app.ai.pricing import estimate_cost  # noqa: PLC0415

    cost = estimate_cost("claude", "claude-opus-99-future", 1_000_000, 0)
    assert cost is not None
    assert abs(cost - 5.0) < 0.001


def test_pricing_claude_haiku() -> None:
    from app.ai.pricing import estimate_cost  # noqa: PLC0415

    cost = estimate_cost("claude", "claude-haiku-4-5", 1_000_000, 1_000_000)
    assert cost is not None
    assert abs(cost - 6.0) < 0.001  # 1+5


def test_pricing_zero_tokens() -> None:
    from app.ai.pricing import estimate_cost  # noqa: PLC0415

    cost = estimate_cost("claude", "claude-opus-4-8", 0, 0)
    assert cost == 0.0
