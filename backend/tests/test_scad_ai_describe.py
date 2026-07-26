"""Tests for 2026-07-25-scad-ai-describe.md.

Coverage:
  1. `extract_scad_header` — deterministic header parsing (unit tests).
  2. Prefill: `process_import_session` sets title/description from a staged
     `.scad`'s header when the session doesn't already have them; never
     overwrites values that are already set.
  3. `POST /api/import-sessions/{id}/ai/describe-scad` — mocked provider,
     no `.scad` staged (400), and no provider configured (graceful 200).

Network calls: ALL mocked. No real Anthropic / OpenAI / Ollama calls.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_provider import AiProvider, AiProviderType
from app.models.import_session import (
    ImportSession,
    ImportSessionFile,
    ImportSessionStatus,
    ImportSourceType,
)
from app.storage.scad_meta import extract_scad_header

# ---------------------------------------------------------------------------
# Sample .scad headers
# ---------------------------------------------------------------------------

_LINE_COMMENT_HEADER = '''// SILICA-SOCK CLAMP  (for 3" / 76mm dust hose)
// ====================================
//
// A clamp that holds a silica gel sock in place inside a dust collection
// hose, preventing it from sliding during operation.
//
// FILES:
//   - clamp_body.stl
//   - clamp_ring.stl
//
// PRINT:
//   - PLA, 20% infill, 0.2mm layer height
//
// HARDWARE:
//   - 2x M3x10 screws
//

$fn = 64;

module clamp() {
    cube([10, 10, 10]);
}
'''

_BLOCK_COMMENT_HEADER = """/*
 * WIDGET STAND
 *
 * Holds a widget upright on a desk. Print at 0.2mm layer height.
 */
$fn = 64;
"""

_CODE_ONLY = "cube([10, 10, 10]);\n$fn = 64;\n"

_DECORATIVE_ONLY = """// PART NAME
// ----------
// Actual body text here.
// ##########
$fn = 1;
"""


# ---------------------------------------------------------------------------
# 1. extract_scad_header unit tests
# ---------------------------------------------------------------------------


def test_extract_scad_header_line_comment_banner() -> None:
    """Title = banner's first line; description carries the FILES/PRINT/HARDWARE notes."""
    result = extract_scad_header(_LINE_COMMENT_HEADER)
    assert result["title"] == 'SILICA-SOCK CLAMP  (for 3" / 76mm dust hose)'
    description = result["description"] or ""
    assert "FILES:" in description
    assert "PRINT:" in description
    assert "HARDWARE:" in description
    assert "clamp_body.stl" in description
    # The title line and decorative rule are not repeated in the description.
    assert "SILICA-SOCK CLAMP" not in description
    assert "====" not in description


def test_extract_scad_header_block_comment() -> None:
    """A leading /* ... */ block header is unwrapped (marker + '*' continuation stripped)."""
    result = extract_scad_header(_BLOCK_COMMENT_HEADER)
    assert result["title"] == "WIDGET STAND"
    assert result["description"] == (
        "Holds a widget upright on a desk. Print at 0.2mm layer height."
    )


def test_extract_scad_header_no_comments_returns_none() -> None:
    """A file that starts directly with code has no usable header."""
    result = extract_scad_header(_CODE_ONLY)
    assert result == {"title": None, "description": None}


def test_extract_scad_header_strips_decorative_rules() -> None:
    """Banner underline/rule lines (=, -, #, whitespace only) are dropped entirely."""
    result = extract_scad_header(_DECORATIVE_ONLY)
    assert result["title"] == "PART NAME"
    assert result["description"] == "Actual body text here."


def test_extract_scad_header_empty_string() -> None:
    """Empty input yields no header."""
    result = extract_scad_header("")
    assert result == {"title": None, "description": None}


# ---------------------------------------------------------------------------
# 2. Prefill on import (process_import_session)
# ---------------------------------------------------------------------------


async def _admin_setup(client: AsyncClient) -> int:
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
    return resp.json()["user_id"]


async def _make_upload_session(
    db_session: AsyncSession,
    user_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
) -> ImportSession:
    session_obj = ImportSession(
        id=uuid.uuid4(),
        status=ImportSessionStatus.processing,
        source_type=ImportSourceType.upload,
        suggested_title=title,
        confirmed_title=title,
        description=description,
        created_by_id=user_id,
    )
    db_session.add(session_obj)
    await db_session.flush()
    return session_obj


async def _stage_scad_file(
    db_session: AsyncSession,
    session_obj: ImportSession,
    tmp_path: Path,
    content: str,
    filename: str = "widget.scad",
) -> ImportSessionFile:
    staged = tmp_path / filename
    staged.write_text(content, encoding="utf-8")
    sf = ImportSessionFile(
        session_id=session_obj.id,
        staged_path=str(staged),
        original_name=filename,
        role="source",
        size=len(content),
    )
    db_session.add(sf)
    await db_session.flush()
    return sf


def _make_session_local_patch(db_session: AsyncSession):  # type: ignore[no-untyped-def]
    """Return a patched SessionLocal that yields db_session (see test_prinnit.py)."""

    def fake_session_local():  # type: ignore[no-untyped-def]
        @asynccontextmanager
        async def _cm():  # type: ignore[no-untyped-def]
            yield db_session

        return _cm()

    return fake_session_local


@pytest.mark.asyncio
async def test_prefill_scad_header_on_empty_upload_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An upload session with no title/description gets them from the .scad header."""
    import app.db as db_mod
    from app.worker.tasks import import_session as wi

    user_id = await _admin_setup(client)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    session_obj = await _make_upload_session(db_session, user_id)
    await _stage_scad_file(db_session, session_obj, tmp_path, _LINE_COMMENT_HEADER)

    await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert session_obj.status == ImportSessionStatus.pending_wizard
    assert session_obj.suggested_title == 'SILICA-SOCK CLAMP  (for 3" / 76mm dust hose)'
    assert session_obj.confirmed_title == 'SILICA-SOCK CLAMP  (for 3" / 76mm dust hose)'
    assert "FILES:" in (session_obj.description or "")


@pytest.mark.asyncio
async def test_prefill_scad_header_never_overwrites_existing_values(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A title/description the user already provided is left untouched."""
    import app.db as db_mod
    from app.worker.tasks import import_session as wi

    user_id = await _admin_setup(client)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    session_obj = await _make_upload_session(
        db_session,
        user_id,
        title="My Custom Title",
        description="My custom description.",
    )
    await _stage_scad_file(db_session, session_obj, tmp_path, _LINE_COMMENT_HEADER)

    await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert session_obj.status == ImportSessionStatus.pending_wizard
    assert session_obj.confirmed_title == "My Custom Title"
    assert session_obj.suggested_title == "My Custom Title"
    assert session_obj.description == "My custom description."


@pytest.mark.asyncio
async def test_prefill_scad_header_noop_when_no_usable_header(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A staged .scad with no comment header leaves title/description unset."""
    import app.db as db_mod
    from app.worker.tasks import import_session as wi

    user_id = await _admin_setup(client)
    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    session_obj = await _make_upload_session(db_session, user_id)
    await _stage_scad_file(db_session, session_obj, tmp_path, _CODE_ONLY)

    await wi.process_import_session({}, str(session_obj.id))

    await db_session.refresh(session_obj)
    assert session_obj.status == ImportSessionStatus.pending_wizard
    assert session_obj.suggested_title is None
    assert session_obj.description is None


# ---------------------------------------------------------------------------
# 3. POST /api/import-sessions/{id}/ai/describe-scad
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_describe_scad_no_provider_returns_graceful_200(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """HEADLINE: describe-scad with no provider → 200, provider_available=False."""
    user_id = await _admin_setup(client)
    csrf = client.cookies.get("pf3d_csrf", "")

    session = await _make_upload_session(db_session, user_id)
    await _stage_scad_file(db_session, session, tmp_path, _LINE_COMMENT_HEADER)

    resp = await client.post(
        f"/api/import-sessions/{session.id}/ai/describe-scad",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is False
    assert data["text"] is None


@pytest.mark.asyncio
async def test_ai_describe_scad_no_scad_file_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """describe-scad on a session with no staged .scad → 400."""
    user_id = await _admin_setup(client)
    csrf = client.cookies.get("pf3d_csrf", "")

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=None,
        enabled=True,
    )
    db_session.add(provider)

    session = await _make_upload_session(db_session, user_id)
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{session.id}/ai/describe-scad",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ai_describe_scad_with_provider_mocked(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """describe-scad with a provider configured sends the whole .scad and returns text."""
    from app.crypto import encrypt

    user_id = await _admin_setup(client)
    csrf = client.cookies.get("pf3d_csrf", "")

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    db_session.add(provider)

    session = await _make_upload_session(db_session, user_id, title="Silica Sock Clamp")
    await _stage_scad_file(db_session, session, tmp_path, _LINE_COMMENT_HEADER)

    captured_user_msg: dict[str, str] = {}

    def fake_caller(api_key, model, system, user_msg, max_tokens):  # type: ignore[no-untyped-def]
        captured_user_msg["value"] = user_msg
        return "A clamp that secures a silica gel sock inside a dust hose."

    with patch("app.ai.client._anthropic_caller", fake_caller):
        resp = await client.post(
            f"/api/import-sessions/{session.id}/ai/describe-scad",
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is True
    assert data["error"] is None
    assert "clamp" in (data["text"] or "").lower()
    # The whole .scad source (not just the header) was sent to the provider.
    assert "module clamp()" in captured_user_msg["value"]


@pytest.mark.asyncio
async def test_ai_describe_scad_ai_error_returns_200_with_error_field(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """When the AI call throws, the endpoint returns 200 with error field — never 5xx."""
    from app.crypto import encrypt

    user_id = await _admin_setup(client)
    csrf = client.cookies.get("pf3d_csrf", "")

    provider = AiProvider(
        provider=AiProviderType.claude,
        model="claude-opus-4-8",
        api_key_encrypted=encrypt("sk-test"),
        enabled=True,
    )
    db_session.add(provider)

    session = await _make_upload_session(db_session, user_id)
    await _stage_scad_file(db_session, session, tmp_path, _LINE_COMMENT_HEADER)

    with patch(
        "app.ai.client._anthropic_caller",
        side_effect=RuntimeError("network down"),
    ):
        resp = await client.post(
            f"/api/import-sessions/{session.id}/ai/describe-scad",
            headers={"x-csrf-token": csrf},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_available"] is True
    assert data["text"] is None
    assert data["error"] is not None
