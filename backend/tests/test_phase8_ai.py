"""Phase 8: AI tagging + provider management tests.

Coverage:
  1. AI client layer — no provider configured (the HEADLINE CONTRACT test).
  2. AI client layer — mocked Claude, OpenAI, and Ollama calls.
  3. Correctness contracts: cap on new suggestions, canonical-only-from-existing,
     error-is-non-fatal (RuntimeError, malformed JSON, empty input).
  4. Default model fallback (claude-opus-4-8 when AiProvider.model is None).
  5. AI provider CRUD via HTTP (admin-gated, key write-only).
  6. AI action endpoints with no provider → graceful empty 200 response.
  7. AI action endpoints with mocked provider → returns AI suggestions.
  8. AI action endpoint where AI errors → 200 with error field (not 5xx).

Network calls: ALL mocked.  No real Anthropic / OpenAI / Ollama calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_provider import AiProvider, AiProviderType

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> str:
    """Initialize instance and return the CSRF token for the admin session."""
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@test.com",
            "admin_name": "Admin User",
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
# 1. HEADLINE CONTRACT: manual-only path works with zero AI configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_enabled_provider_returns_none_when_no_providers(
    db_session: AsyncSession,
) -> None:
    """get_enabled_provider returns None when no AiProvider rows exist."""
    from app.ai.client import get_enabled_provider

    result = await get_enabled_provider(db_session)
    assert result is None


@pytest.mark.asyncio
async def test_ai_suggest_tags_no_provider_returns_graceful_200(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """HEADLINE: suggest-tags with no provider configured → 200, provider_available=False."""
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
        suggested_title="Bracket V2",
        confirmed_title="Bracket V2",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{session.id}/ai/suggest-tags",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is False
    assert data["canonical"] == []
    assert data["new_suggestions"] == []
    assert data["error"] is None


@pytest.mark.asyncio
async def test_ai_cleanup_description_no_provider_returns_graceful_200(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """HEADLINE: cleanup-description with no provider → 200, provider_available=False."""
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
        confirmed_title="Design A",
        description="bad grammer here",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{session.id}/ai/cleanup-description",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is False
    assert data["text"] is None


@pytest.mark.asyncio
async def test_ai_summarize_no_provider_returns_graceful_200(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """HEADLINE: summarize with no provider → 200, provider_available=False."""
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
        source_type=ImportSourceType.url,
        source_url="https://example.com/thing",
        confirmed_title="Some Design",
        description="long scraped text here",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{session.id}/ai/summarize",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is False
    assert data["text"] is None


# ---------------------------------------------------------------------------
# 2. AI client layer — mocked provider calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_tags_claude_mocked(tmp_path: Path) -> None:
    """suggest_tags returns canonical + new_suggestions from a mocked Claude response."""
    from app.ai.client import AiTagResult, suggest_tags  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    mock_json = json.dumps({
        "canonical": ["3d-printing", "fdm"],
        "new_suggestions": ["articulated-joint"],
    })

    with patch(
        "app.ai.client._anthropic_caller",
        lambda _key, _model, _sys, _usr, _tok: mock_json,
    ):
        result = suggest_tags(
            provider=provider,
            title="Articulated Snake",
            description="A flexible articulated snake toy",
            scraped_text=None,
            filenames=["snake.stl", "snake-readme.txt"],
            existing_tags=["3d-printing", "fdm", "toys", "functional"],
        )

    assert isinstance(result, AiTagResult)
    assert "3d-printing" in result.canonical
    assert "fdm" in result.canonical
    assert "articulated-joint" in result.new_suggestions
    assert result.error is None


@pytest.mark.asyncio
async def test_suggest_tags_openai_mocked(tmp_path: Path) -> None:
    """suggest_tags works with an OpenAI provider."""
    from app.ai.client import suggest_tags  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.openai,
        model="gpt-4o-mini",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    mock_json = json.dumps({"canonical": ["fdm"], "new_suggestions": ["wall-bracket"]})

    with patch(
        "app.ai.client._openai_caller",
        lambda _key, _url, _model, _sys, _usr, _tok: mock_json,
    ):
        result = suggest_tags(
            provider=provider,
            title="Wall Bracket",
            description=None,
            scraped_text="a bracket for mounting",
            filenames=[],
            existing_tags=["fdm", "resin", "functional"],
        )

    assert "fdm" in result.canonical
    assert "wall-bracket" in result.new_suggestions


@pytest.mark.asyncio
async def test_suggest_tags_ollama_uses_base_url(tmp_path: Path) -> None:
    """Ollama provider passes its endpoint as base_url to the openai caller."""
    from app.ai.client import suggest_tags  # noqa: PLC0415

    captured: dict = {}

    def mock_openai(api_key, base_url, model, system, user_msg, max_tokens):
        captured["base_url"] = base_url
        return json.dumps({"canonical": [], "new_suggestions": []})

    provider = AiProvider(
        provider=AiProviderType.ollama,
        endpoint="http://localhost:11434/v1",
        model="llama3",
        api_key_encrypted=None,
        enabled=True,
    )

    with patch("app.ai.client._openai_caller", mock_openai):
        suggest_tags(
            provider=provider,
            title="T",
            description=None,
            scraped_text=None,
            filenames=[],
            existing_tags=[],
        )

    assert captured.get("base_url") == "http://localhost:11434/v1"


# ---------------------------------------------------------------------------
# 3. Correctness contracts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_tags_caps_new_suggestions_at_max(tmp_path: Path) -> None:
    """new_suggestions is capped at MAX_NEW_SUGGESTIONS regardless of AI output."""
    from app.ai.client import MAX_NEW_SUGGESTIONS, suggest_tags  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    # AI returns 10 suggestions — should be trimmed to MAX_NEW_SUGGESTIONS
    oversized = json.dumps({
        "canonical": [],
        "new_suggestions": [f"tag-{i}" for i in range(10)],
    })

    with patch("app.ai.client._anthropic_caller", lambda *a: oversized):
        result = suggest_tags(
            provider=provider, title="T", description=None,
            scraped_text=None, filenames=[], existing_tags=[],
        )

    assert len(result.new_suggestions) <= MAX_NEW_SUGGESTIONS


@pytest.mark.asyncio
async def test_suggest_tags_canonical_filtered_to_existing_tags(tmp_path: Path) -> None:
    """canonical only contains tags that appear in existing_tags; hallucinations stripped."""
    from app.ai.client import suggest_tags  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    # AI returns "fdm" (valid) + "hallucinated" (not in existing_tags)
    mock_json = json.dumps({"canonical": ["fdm", "hallucinated"], "new_suggestions": []})

    with patch("app.ai.client._anthropic_caller", lambda *a: mock_json):
        result = suggest_tags(
            provider=provider, title="T", description=None,
            scraped_text=None, filenames=[], existing_tags=["fdm", "resin"],
        )

    assert "fdm" in result.canonical
    assert "hallucinated" not in result.canonical


@pytest.mark.asyncio
async def test_suggest_tags_runtime_error_is_non_fatal(tmp_path: Path) -> None:
    """RuntimeError from AI call returns AiTagResult with error — never raises."""
    from app.ai.client import suggest_tags  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    with patch("app.ai.client._anthropic_caller", side_effect=RuntimeError("network down")):
        result = suggest_tags(
            provider=provider, title="T", description=None,
            scraped_text=None, filenames=[], existing_tags=[],
        )

    assert result.error is not None
    assert result.canonical == []
    assert result.new_suggestions == []


@pytest.mark.asyncio
async def test_suggest_tags_malformed_json_is_non_fatal(tmp_path: Path) -> None:
    """Malformed JSON from AI returns AiTagResult with error — never raises."""
    from app.ai.client import suggest_tags  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    with patch("app.ai.client._anthropic_caller", lambda *a: "not valid json {{{"):
        result = suggest_tags(
            provider=provider, title="T", description=None,
            scraped_text=None, filenames=[], existing_tags=[],
        )

    assert result.error is not None
    assert result.canonical == []


@pytest.mark.asyncio
async def test_cleanup_description_empty_input_is_non_fatal(tmp_path: Path) -> None:
    """cleanup_description with empty description returns error, never raises."""
    from app.ai.client import cleanup_description  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    result = cleanup_description(provider=provider, description="", title="T")
    assert result.error is not None
    assert result.text is None


@pytest.mark.asyncio
async def test_summarize_empty_scraped_text_is_non_fatal(tmp_path: Path) -> None:
    """summarize_scrape with empty text returns error, never raises."""
    from app.ai.client import summarize_scrape  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    result = summarize_scrape(provider=provider, scraped_text="  ", title="T")
    assert result.error is not None
    assert result.text is None


@pytest.mark.asyncio
async def test_cleanup_description_mocked(tmp_path: Path) -> None:
    """cleanup_description returns the cleaned text from AI."""
    from app.ai.client import cleanup_description  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    with patch("app.ai.client._anthropic_caller", lambda *a: "A well-formed description."):
        result = cleanup_description(
            provider=provider, description="bad grammer here", title="My Design"
        )

    assert result.text == "A well-formed description."
    assert result.error is None


@pytest.mark.asyncio
async def test_summarize_scrape_mocked(tmp_path: Path) -> None:
    """summarize_scrape returns a summary from AI."""
    from app.ai.client import summarize_scrape  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    with patch("app.ai.client._anthropic_caller", lambda *a: "Compact summary here."):
        result = summarize_scrape(
            provider=provider,
            scraped_text="lots of scraped web text here",
            title="Some Design",
        )

    assert result.text == "Compact summary here."
    assert result.error is None


# ---------------------------------------------------------------------------
# 4. Default model fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_claude_model_is_claude_opus_4_8(tmp_path: Path) -> None:
    """When AiProvider.model is None, the Claude call uses 'claude-opus-4-8'."""
    from app.ai.client import suggest_tags  # noqa: PLC0415
    from app.crypto import encrypt, ensure_key  # noqa: PLC0415

    ensure_key()

    provider = AiProvider(
        provider=AiProviderType.claude,
        model=None,  # intentionally unset
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )

    captured: dict = {}

    def mock_caller(api_key, model, system, user_msg, max_tokens):
        captured["model"] = model
        return json.dumps({"canonical": [], "new_suggestions": []})

    with patch("app.ai.client._anthropic_caller", mock_caller):
        suggest_tags(
            provider=provider, title="T", description=None,
            scraped_text=None, filenames=[], existing_tags=[],
        )

    assert captured.get("model") == "claude-opus-4-8"


# ---------------------------------------------------------------------------
# 5. AI Provider CRUD (admin-gated HTTP endpoints)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_ai_providers_empty(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    """Empty list when no providers configured."""
    csrf = await _setup_and_login(client)
    resp = await client.get("/api/ai-providers", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_ai_provider_key_never_returned(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    """Creating a provider stores the key encrypted; response never exposes it."""
    csrf = await _setup_and_login(client)
    resp = await client.post(
        "/api/ai-providers",
        json={
            "provider": "claude",
            "model": "claude-opus-4-8",
            "api_key": "my-secret-key",
            "enabled": False,
        },
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "claude"
    assert data["model"] == "claude-opus-4-8"
    assert data["has_key"] is True
    assert "api_key" not in data
    assert "api_key_encrypted" not in data


@pytest.mark.asyncio
async def test_create_ai_provider_invalid_type_returns_422(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    csrf = await _setup_and_login(client)
    resp = await client.post(
        "/api/ai-providers",
        json={"provider": "not-a-real-provider"},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_ai_provider(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    csrf = await _setup_and_login(client)

    create_resp = await client.post(
        "/api/ai-providers",
        json={"provider": "openai", "model": "gpt-4", "enabled": False},
        headers={"x-csrf-token": csrf},
    )
    pid = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/ai-providers/{pid}",
        json={"enabled": True, "model": "gpt-4o"},
        headers={"x-csrf-token": csrf},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["enabled"] is True
    assert data["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_delete_ai_provider(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    csrf = await _setup_and_login(client)

    create_resp = await client.post(
        "/api/ai-providers",
        json={"provider": "ollama", "endpoint": "http://localhost:11434/v1", "model": "llama3"},
        headers={"x-csrf-token": csrf},
    )
    pid = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/ai-providers/{pid}",
        headers={"x-csrf-token": csrf},
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/ai-providers/{pid}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_enable_ai_provider_toggle(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    csrf = await _setup_and_login(client)

    create_resp = await client.post(
        "/api/ai-providers",
        json={"provider": "claude", "enabled": False},
        headers={"x-csrf-token": csrf},
    )
    pid = create_resp.json()["id"]

    enable_resp = await client.post(
        f"/api/ai-providers/{pid}/enable",
        json={"enabled": True},
        headers={"x-csrf-token": csrf},
    )
    assert enable_resp.status_code == 200
    assert enable_resp.json()["enabled"] is True

    disable_resp = await client.post(
        f"/api/ai-providers/{pid}/enable",
        json={"enabled": False},
        headers={"x-csrf-token": csrf},
    )
    assert disable_resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_get_ai_provider_404(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    await _setup_and_login(client)
    resp = await client.get("/api/ai-providers/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ai_provider_non_admin_forbidden(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    """Non-admin users cannot access AI provider endpoints."""
    from app.auth.password import hash_password  # noqa: PLC0415
    from app.models.user import User, UserRole  # noqa: PLC0415

    await _setup_and_login(client)

    # Create a regular user
    regular_user = User(
        email="user@test.com",
        name="Regular User",
        role=UserRole.user,
        password_hash=hash_password("userpass1"),
    )
    db_session.add(regular_user)
    await db_session.flush()

    # Login as regular user
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "user@test.com", "password": "userpass1"},
    )
    assert login_resp.status_code == 200
    user_csrf = client.cookies.get("pf3d_csrf", "")

    resp = await client.get("/api/ai-providers", headers={"x-csrf-token": user_csrf})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6–7. AI action endpoints — with mocked provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_suggest_tags_with_provider_mocked(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    """suggest-tags with an enabled provider returns AI suggestions (mocked)."""
    from app.crypto import encrypt  # noqa: PLC0415
    from app.models.import_session import (  # noqa: PLC0415
        ImportSession,
        ImportSessionStatus,
        ImportSourceType,
    )
    from app.models.tag import Tag, TagStatus  # noqa: PLC0415
    from app.models.user import User  # noqa: PLC0415

    csrf = await _setup_and_login(client)

    user_res = await db_session.execute(select(User).limit(1))
    admin = user_res.scalar_one()

    # Create some active tags
    tag_fdm = Tag(name="fdm", status=TagStatus.active)
    db_session.add(tag_fdm)
    await db_session.flush()

    # Create an enabled AI provider
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
        confirmed_title="Cool FDM Bracket",
        description="A bracket for mounting electronics",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    mock_json = json.dumps({"canonical": ["fdm"], "new_suggestions": ["wall-bracket"]})

    with patch("app.ai.client._anthropic_caller", lambda *a: mock_json):
        resp = await client.post(
            f"/api/import-sessions/{session.id}/ai/suggest-tags",
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is True
    assert "fdm" in data["canonical"]
    assert "wall-bracket" in data["new_suggestions"]
    assert data["error"] is None


@pytest.mark.asyncio
async def test_ai_cleanup_description_with_provider_mocked(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    """cleanup-description with provider configured returns cleaned text."""
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
        confirmed_title="Test Design",
        description="a description with bad grammer",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    with patch(
        "app.ai.client._anthropic_caller",
        lambda *a: "A description with correct grammar.",
    ):
        resp = await client.post(
            f"/api/import-sessions/{session.id}/ai/cleanup-description",
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is True
    assert data["text"] == "A description with correct grammar."
    assert data["error"] is None


@pytest.mark.asyncio
async def test_ai_summarize_with_provider_mocked(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    """summarize with provider configured returns a summary draft."""
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
        source_type=ImportSourceType.url,
        source_url="https://www.thingiverse.com/thing:12345",
        confirmed_title="Articulated Dragon",
        description="Long scraped page text about an articulated dragon model",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    with patch(
        "app.ai.client._anthropic_caller",
        lambda *a: "An articulated dragon model with movable joints.",
    ):
        resp = await client.post(
            f"/api/import-sessions/{session.id}/ai/summarize",
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is True
    assert "dragon" in (data["text"] or "").lower()
    assert data["error"] is None


# ---------------------------------------------------------------------------
# 8. AI error → 200 with error field (not 5xx)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_suggest_tags_ai_error_returns_200_with_error_field(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    """When the AI call throws, the endpoint returns 200 with error field — never 5xx."""
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
        confirmed_title="Test",
        created_by_id=admin.id,
    )
    db_session.add(session)
    await db_session.flush()

    with patch(
        "app.ai.client._anthropic_caller",
        side_effect=RuntimeError("Simulated network failure"),
    ):
        resp = await client.post(
            f"/api/import-sessions/{session.id}/ai/suggest-tags",
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is True
    assert data["error"] is not None
    assert data["canonical"] == []
    assert data["new_suggestions"] == []


@pytest.mark.asyncio
async def test_test_endpoint_uses_saved_provider_key(client: AsyncClient) -> None:
    """POST /api/ai-providers/test with provider_id (no api_key) reuses the stored
    key — regression for the 'Could not resolve authentication' error when testing
    a saved provider without re-entering its write-only key."""
    csrf = await _setup_and_login(client)

    # Save a Claude provider WITH a key.
    create = await client.post(
        "/api/ai-providers",
        json={"provider": "claude", "model": "claude-opus-4-8", "api_key": "sk-test"},
        headers={"x-csrf-token": csrf},
    )
    assert create.status_code == 201
    pid = create.json()["id"]

    # Test it WITHOUT sending the key — must reuse the stored one (mock the SDK).
    with patch(
        "app.ai.client._anthropic_caller",
        lambda _key, _model, _sys, _usr, _tok: "ok" if _key == "sk-test" else None,
    ):
        resp = await client.post(
            "/api/ai-providers/test",
            json={"provider": "claude", "provider_id": pid},
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_test_endpoint_no_key_returns_clear_error(client: AsyncClient) -> None:
    """Testing claude/openai with neither a key nor a provider_id returns a clear
    message instead of the SDK's cryptic auth error."""
    csrf = await _setup_and_login(client)

    resp = await client.post(
        "/api/ai-providers/test",
        json={"provider": "claude"},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "api key" in (body["error"] or "").lower()
