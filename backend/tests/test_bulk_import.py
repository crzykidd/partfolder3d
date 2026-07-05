"""Tests for bulk-import feature (issue #15).

Covers:
  A. POST /api/import-sessions/bulk-commit
     - returns correct summary shape (total, committed, skipped, errors)
     - skips sessions with wrong status, no title, no resolvable library
     - commits valid pending_wizard sessions
     - per-session isolation: one failure does not roll back others
     - library resolution order (override > session > setting > sole-lib > skip)

  B. import.default_library_id setting
     - set and retrieve
     - rejects non-integer values
     - rejects disabled/non-existent library IDs
     - accepts null (clear)

  C. _resolve_import_library helper
     - direct unit-test of resolution order

Bulk-commit uses an internal SessionLocal() per session.  To make test data
visible across that boundary we monkeypatch app.db.SessionLocal inside the
function to reuse the test's db_session.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_session import (
    ImportSession,
    ImportSessionStatus,
    ImportSourceType,
)
from app.models.library import Library

# ---------------------------------------------------------------------------
# Auth + setup helpers
# ---------------------------------------------------------------------------


async def _admin_setup(client: AsyncClient, tmp_path: Path) -> tuple[str, int]:
    """Initialize instance, log in as admin. Returns (csrf_token, user_id)."""
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
    csrf = client.cookies.get("pf3d_csrf", "")
    user_id: int = resp.json()["user_id"]
    return csrf, user_id


async def _create_library(
    client: AsyncClient, csrf: str, name: str, mount_path: Path
) -> int:
    mount_path.mkdir(parents=True, exist_ok=True)
    resp = await client.post(
        "/api/libraries",
        json={"name": name, "mount_path": str(mount_path)},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_pending_session(
    db_session: AsyncSession,
    user_id: int,
    library_id: int | None,
    confirmed_title: str | None = "Test Item",
    status: ImportSessionStatus = ImportSessionStatus.pending_wizard,
) -> ImportSession:
    """Directly insert a session into the test transaction."""
    session_obj = ImportSession(
        id=uuid.uuid4(),
        status=status,
        source_type=ImportSourceType.upload,
        confirmed_title=confirmed_title,
        library_id=library_id,
        created_by_id=user_id,
    )
    db_session.add(session_obj)
    await db_session.flush()
    return session_obj


def _make_session_local_patch(db_session: AsyncSession):
    """Return a patched SessionLocal that yields db_session."""

    def fake_session_local():
        @asynccontextmanager
        async def _cm():
            yield db_session

        return _cm()

    return fake_session_local


# ---------------------------------------------------------------------------
# A. Bulk-commit summary shape and preconditions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_commit_empty_list(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST bulk-commit with empty session_ids returns zero totals."""
    csrf, _ = await _admin_setup(client, tmp_path)

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": []},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["committed"] == 0
    assert data["skipped"] == []
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_bulk_commit_invalid_uuid_skipped(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Invalid UUID in session_ids → skipped with reason='invalid_id'."""
    csrf, _ = await _admin_setup(client, tmp_path)

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": ["not-a-uuid"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["committed"] == 0
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["reason"] == "invalid_id"


@pytest.mark.asyncio
async def test_bulk_commit_nonexistent_session_skipped(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session ID that doesn't exist → skipped with reason='not_found'."""
    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    csrf, _ = await _admin_setup(client, tmp_path)
    fake_id = str(uuid.uuid4())

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": [fake_id]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["committed"] == 0
    assert data["skipped"][0]["session_id"] == fake_id
    assert data["skipped"][0]["reason"] == "not_found"


@pytest.mark.asyncio
async def test_bulk_commit_skips_wrong_status(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sessions not in pending_wizard status are skipped."""
    csrf, user_id = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Test Lib", tmp_path / "lib")

    draft_sess = await _make_pending_session(
        db_session, user_id, lib_id, status=ImportSessionStatus.draft
    )
    committed_sess = await _make_pending_session(
        db_session, user_id, lib_id, status=ImportSessionStatus.committed
    )

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": [str(draft_sess.id), str(committed_sess.id)]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["committed"] == 0
    assert len(data["skipped"]) == 2
    reasons = {s["reason"] for s in data["skipped"]}
    assert "wrong_status:draft" in reasons
    assert "wrong_status:committed" in reasons


@pytest.mark.asyncio
async def test_bulk_commit_skips_no_title(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sessions with no confirmed_title or suggested_title are skipped."""
    csrf, user_id = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Test Lib", tmp_path / "lib")

    sess = await _make_pending_session(
        db_session, user_id, lib_id, confirmed_title=None
    )

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": [str(sess.id)]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["committed"] == 0
    assert data["skipped"][0]["reason"] == "no_title"


@pytest.mark.asyncio
async def test_bulk_commit_skips_no_library(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sessions with no resolvable library are skipped with reason='no_library'."""
    csrf, user_id = await _admin_setup(client, tmp_path)
    # Do NOT create a library — ensure no sole-lib fallback either
    # (but setup created some default settings; need to make sure no library exists)
    # Since we're in a rolled-back transaction, any libraries from previous tests
    # are gone. Just create the session without a library_id.
    sess = await _make_pending_session(db_session, user_id, library_id=None)

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": [str(sess.id)]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["committed"] == 0
    assert data["skipped"][0]["reason"] == "no_library"


@pytest.mark.asyncio
async def test_bulk_commit_commits_valid_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid pending_wizard session with a library is committed."""
    csrf, user_id = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Test Lib", tmp_path / "lib")

    sess = await _make_pending_session(
        db_session, user_id, lib_id, confirmed_title="My Test Item"
    )

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": [str(sess.id)]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["committed"] == 1
    assert data["skipped"] == []
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_bulk_commit_partial_success(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mix of valid and invalid sessions → partial success.

    Creates two libraries (making auto-resolution ambiguous) so a session
    with no library_id can't be resolved → skipped with 'no_library'.
    """
    csrf, user_id = await _admin_setup(client, tmp_path)
    # Two libraries → auto-resolution (sole-lib fallback) won't apply
    lib_a_id = await _create_library(client, csrf, "Lib A", tmp_path / "lib_a")
    _lib_b_id = await _create_library(client, csrf, "Lib B", tmp_path / "lib_b")

    good_sess = await _make_pending_session(
        db_session, user_id, lib_a_id, confirmed_title="Good Item"
    )
    no_title_sess = await _make_pending_session(
        db_session, user_id, lib_a_id, confirmed_title=None
    )
    # session with no library_id + 2 libraries → no_library (ambiguous)
    no_lib_sess = await _make_pending_session(
        db_session, user_id, library_id=None, confirmed_title="No Lib Item"
    )

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={
            "session_ids": [
                str(good_sess.id),
                str(no_title_sess.id),
                str(no_lib_sess.id),
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["committed"] == 1
    assert len(data["skipped"]) == 2
    skip_reasons = {s["reason"] for s in data["skipped"]}
    assert "no_title" in skip_reasons
    assert "no_library" in skip_reasons


@pytest.mark.asyncio
async def test_bulk_commit_null_session_ids_targets_all_pending(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """session_ids=null → all pending_wizard sessions visible to caller."""
    csrf, user_id = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Test Lib", tmp_path / "lib")

    await _make_pending_session(
        db_session, user_id, lib_id, confirmed_title="Item A"
    )
    await _make_pending_session(
        db_session, user_id, lib_id, confirmed_title="Item B"
    )
    # Draft session should NOT be included in null target
    await _make_pending_session(
        db_session, user_id, lib_id, status=ImportSessionStatus.draft
    )

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    # total should be 2 (the two pending_wizard, not the draft)
    assert data["total"] == 2
    assert data["committed"] == 2


@pytest.mark.asyncio
async def test_bulk_commit_library_override(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """library_id override in request body takes priority over session's library_id."""
    csrf, user_id = await _admin_setup(client, tmp_path)
    # Create two libraries: lib_a on the session, lib_b as override
    lib_a_id = await _create_library(client, csrf, "Lib A", tmp_path / "lib_a")
    lib_b_id = await _create_library(client, csrf, "Lib B", tmp_path / "lib_b")

    sess = await _make_pending_session(
        db_session, user_id, lib_a_id, confirmed_title="Override Test"
    )

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": [str(sess.id)], "library_id": lib_b_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["committed"] == 1

    # Verify the item landed in lib_b, not lib_a
    result = await db_session.execute(
        select(ImportSession).where(ImportSession.id == sess.id)
    )
    updated_sess = result.scalar_one()
    assert updated_sess.status == ImportSessionStatus.committed
    assert updated_sess.item_id is not None

    from app.models.item import Item  # noqa: PLC0415

    item_res = await db_session.execute(
        select(Item).where(Item.id == updated_sess.item_id)
    )
    item = item_res.scalar_one()
    assert item.library_id == lib_b_id


@pytest.mark.asyncio
async def test_bulk_commit_requires_auth(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/import-sessions/bulk-commit requires authentication."""
    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": []},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bulk_commit_requires_csrf(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/import-sessions/bulk-commit requires CSRF token."""
    await _admin_setup(client, tmp_path)
    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": []},
        # No X-CSRF-Token header
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# B. import.default_library_id setting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_library_setting_set_and_get(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Admin can set import.default_library_id to an enabled library."""
    csrf, _ = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Default Lib", tmp_path / "lib")

    resp = await client.put(
        "/api/settings/import.default_library_id",
        json={"value": lib_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == lib_id
    assert resp.json()["key"] == "import.default_library_id"

    # Verify in list
    list_resp = await client.get("/api/settings")
    assert list_resp.status_code == 200
    keys = {s["key"]: s["value"] for s in list_resp.json()}
    assert keys.get("import.default_library_id") == lib_id


@pytest.mark.asyncio
async def test_default_library_setting_can_be_cleared_with_null(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """import.default_library_id can be cleared by setting to null."""
    csrf, _ = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Lib", tmp_path / "lib")

    # Set then clear
    await client.put(
        "/api/settings/import.default_library_id",
        json={"value": lib_id},
        headers={"X-CSRF-Token": csrf},
    )
    clear_resp = await client.put(
        "/api/settings/import.default_library_id",
        json={"value": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["value"] is None


@pytest.mark.asyncio
async def test_default_library_setting_rejects_non_integer(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """import.default_library_id rejects non-integer values (string, bool)."""
    csrf, _ = await _admin_setup(client, tmp_path)

    for bad_value in ["not-a-number", True, 3.14, [1]]:
        resp = await client.put(
            "/api/settings/import.default_library_id",
            json={"value": bad_value},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422, f"Expected 422 for value={bad_value!r}"


@pytest.mark.asyncio
async def test_default_library_setting_rejects_nonexistent_library(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """import.default_library_id rejects an integer that doesn't match any library."""
    csrf, _ = await _admin_setup(client, tmp_path)

    resp = await client.put(
        "/api/settings/import.default_library_id",
        json={"value": 99999},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_default_library_setting_rejects_disabled_library(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """import.default_library_id rejects a disabled library."""
    csrf, _ = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Lib", tmp_path / "lib")

    # Disable the library via DELETE (soft-delete)
    del_resp = await client.delete(
        f"/api/libraries/{lib_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204

    resp = await client.put(
        "/api/settings/import.default_library_id",
        json={"value": lib_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# C. _resolve_import_library — direct unit test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_library_override_wins(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Override library_id (a) takes priority over session library_id (b)."""
    from app.routers.import_sessions.sessions import _resolve_import_library  # noqa: PLC0415

    csrf, _ = await _admin_setup(client, tmp_path)
    lib_a_path = tmp_path / "lib_a"
    lib_a_path.mkdir()
    lib_b_path = tmp_path / "lib_b"
    lib_b_path.mkdir()

    lib_a = Library(name="Lib A", mount_path=str(lib_a_path))
    lib_b = Library(name="Lib B", mount_path=str(lib_b_path))
    db_session.add(lib_a)
    db_session.add(lib_b)
    await db_session.flush()

    result = await _resolve_import_library(lib_a.id, lib_b.id, db_session)
    assert result is not None
    assert result.id == lib_a.id


@pytest.mark.asyncio
async def test_resolve_library_session_lib_when_no_override(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Session library_id (b) used when no override provided."""
    from app.routers.import_sessions.sessions import _resolve_import_library  # noqa: PLC0415

    csrf, _ = await _admin_setup(client, tmp_path)
    lib_path = tmp_path / "lib"
    lib_path.mkdir()

    lib = Library(name="Session Lib", mount_path=str(lib_path))
    db_session.add(lib)
    await db_session.flush()

    result = await _resolve_import_library(None, lib.id, db_session)
    assert result is not None
    assert result.id == lib.id


@pytest.mark.asyncio
async def test_resolve_library_setting_fallback(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Default-library setting (c) used when no override or session lib."""
    import json  # noqa: PLC0415

    from app.models.setting import Setting  # noqa: PLC0415
    from app.routers.import_sessions.sessions import _resolve_import_library  # noqa: PLC0415

    await _admin_setup(client, tmp_path)
    lib_path = tmp_path / "lib"
    lib_path.mkdir()

    lib = Library(name="Default Lib", mount_path=str(lib_path))
    db_session.add(lib)
    await db_session.flush()

    # Set the setting directly in the test transaction
    setting = Setting(key="import.default_library_id", value=json.dumps(lib.id))
    db_session.add(setting)
    await db_session.flush()

    result = await _resolve_import_library(None, None, db_session)
    assert result is not None
    assert result.id == lib.id


@pytest.mark.asyncio
async def test_resolve_library_sole_lib_fallback(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Sole enabled library (d) used when no override, session lib, or setting."""
    from app.routers.import_sessions.sessions import _resolve_import_library  # noqa: PLC0415

    await _admin_setup(client, tmp_path)
    lib_path = tmp_path / "lib"
    lib_path.mkdir()

    lib = Library(name="Only Lib", mount_path=str(lib_path))
    db_session.add(lib)
    await db_session.flush()

    result = await _resolve_import_library(None, None, db_session)
    assert result is not None
    assert result.id == lib.id


@pytest.mark.asyncio
async def test_resolve_library_none_when_ambiguous(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """None returned when multiple libraries exist and no other resolution."""
    from app.routers.import_sessions.sessions import _resolve_import_library  # noqa: PLC0415

    await _admin_setup(client, tmp_path)

    lib_a = Library(name="Lib A", mount_path=str(tmp_path / "lib_a"))
    lib_b = Library(name="Lib B", mount_path=str(tmp_path / "lib_b"))
    (tmp_path / "lib_a").mkdir()
    (tmp_path / "lib_b").mkdir()
    db_session.add(lib_a)
    db_session.add(lib_b)
    await db_session.flush()

    result = await _resolve_import_library(None, None, db_session)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_library_skips_disabled(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Disabled libraries are not eligible for resolution."""
    from app.routers.import_sessions.sessions import _resolve_import_library  # noqa: PLC0415

    await _admin_setup(client, tmp_path)
    lib_path = tmp_path / "lib"
    lib_path.mkdir()

    lib = Library(name="Disabled Lib", mount_path=str(lib_path), enabled=False)
    db_session.add(lib)
    await db_session.flush()

    # Even if it's the only "library", it's disabled → None
    result = await _resolve_import_library(None, lib.id, db_session)
    assert result is None


# ---------------------------------------------------------------------------
# D. render preference
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_commit_render_off_skips_enqueue(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """render='off' in bulk-commit → _enqueue_render is NOT called."""
    import app.db as db_mod
    import app.routers.import_sessions.sessions as sessions_mod

    csrf, user_id = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Test Lib", tmp_path / "lib")
    sess = await _make_pending_session(
        db_session, user_id, lib_id, confirmed_title="Render Off Item"
    )

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    render_calls: list[int] = []

    async def fake_enqueue_render(
        item_id: int, *, pool=None, db=None, model_extensions=None
    ) -> None:
        render_calls.append(item_id)

    monkeypatch.setattr(sessions_mod, "_enqueue_render", fake_enqueue_render)

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": [str(sess.id)], "render": "off"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["committed"] == 1
    assert render_calls == []


@pytest.mark.asyncio
async def test_bulk_commit_render_auto_enqueues(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """render='auto' (default) in bulk-commit → _enqueue_render IS called."""
    import app.db as db_mod
    import app.routers.import_sessions.sessions as sessions_mod

    csrf, user_id = await _admin_setup(client, tmp_path)
    lib_id = await _create_library(client, csrf, "Test Lib", tmp_path / "lib")
    sess = await _make_pending_session(
        db_session, user_id, lib_id, confirmed_title="Render Auto Item"
    )

    monkeypatch.setattr(db_mod, "SessionLocal", _make_session_local_patch(db_session))

    render_calls: list[int] = []

    async def fake_enqueue_render(
        item_id: int, *, pool=None, db=None, model_extensions=None
    ) -> None:
        render_calls.append(item_id)

    monkeypatch.setattr(sessions_mod, "_enqueue_render", fake_enqueue_render)

    resp = await client.post(
        "/api/import-sessions/bulk-commit",
        json={"session_ids": [str(sess.id)]},  # render omitted → default "auto"
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["committed"] == 1
    assert len(render_calls) == 1
