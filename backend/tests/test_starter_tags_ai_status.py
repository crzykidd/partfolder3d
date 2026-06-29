"""Tests for Phase (starter tags + cheap AI status endpoint).

Coverage:
  1. POST /api/tags/load-defaults inserts the full starter set as active tags.
  2. POST /api/tags/load-defaults is idempotent (second call adds 0, skips all).
  3. GET /api/ai/status returns provider_available=false with no provider configured.
  4. GET /api/ai/status returns provider_available=true with an enabled provider,
     and writes NO ai_usage row.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag, TagStatus
from app.tags_defaults import STARTER_TAGS

# ---------------------------------------------------------------------------
# Auth helper (shared with other phase test files)
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> str:
    """Run first-time setup and return the CSRF token for the admin session."""
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
# 1 + 2: load-defaults — inserts active tags, idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_defaults_inserts_active_tags(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /api/tags/load-defaults inserts every starter tag as status=active."""
    csrf = await _setup_and_login(client)

    resp = await client.post(
        "/api/tags/load-defaults",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    expected_count = len(STARTER_TAGS)
    assert data["added"] == expected_count, f"expected {expected_count} added, got {data}"
    assert data["skipped"] == 0

    # Verify DB rows: all starter names present and active.
    result = await db_session.execute(
        select(Tag).where(Tag.status == TagStatus.active)
    )
    active_tags = result.scalars().all()
    active_names = {t.name for t in active_tags}

    for name, category in STARTER_TAGS:
        assert name in active_names, f"Expected tag '{name}' to be present"
        # Find and check category.
        tag_row = next(t for t in active_tags if t.name == name)
        assert tag_row.category == category, (
            f"Tag '{name}': expected category '{category}', got '{tag_row.category}'"
        )


@pytest.mark.asyncio
async def test_load_defaults_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Second call to POST /api/tags/load-defaults adds 0 new tags."""
    csrf = await _setup_and_login(client)

    # First call
    resp1 = await client.post(
        "/api/tags/load-defaults",
        headers={"x-csrf-token": csrf},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["added"] == len(STARTER_TAGS)

    # Second call — must be fully idempotent
    resp2 = await client.post(
        "/api/tags/load-defaults",
        headers={"x-csrf-token": csrf},
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["added"] == 0, f"Second call should add 0, got {data2}"
    assert data2["skipped"] == len(STARTER_TAGS)


# ---------------------------------------------------------------------------
# 3: GET /api/ai/status — no provider → false
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_status_no_provider(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/ai/status returns provider_available=false when no provider is configured."""
    await _setup_and_login(client)

    resp = await client.get("/api/ai/status")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data == {"provider_available": False}


# ---------------------------------------------------------------------------
# 4: GET /api/ai/status — enabled provider → true, NO ai_usage row written
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_status_with_enabled_provider_no_usage_row(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/ai/status returns true when a provider is enabled and writes NO ai_usage row."""
    from app.models.ai_provider import AiProvider, AiProviderType
    from app.models.ai_usage import AiUsage

    await _setup_and_login(client)

    # Insert an enabled provider (Ollama — no real key needed for the status check).
    provider = AiProvider(
        provider=AiProviderType.ollama,
        endpoint="http://localhost:11434",
        model="llama3",
        api_key_encrypted=None,
        enabled=True,
    )
    db_session.add(provider)
    await db_session.flush()

    # Count ai_usage rows before the call.
    before_result = await db_session.execute(select(AiUsage))
    usage_before = len(before_result.scalars().all())

    resp = await client.get("/api/ai/status")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data == {"provider_available": True}

    # Count ai_usage rows after — must not have increased.
    after_result = await db_session.execute(select(AiUsage))
    usage_after = len(after_result.scalars().all())
    assert usage_after == usage_before, (
        f"GET /api/ai/status wrote {usage_after - usage_before} ai_usage row(s) — must write 0"
    )
