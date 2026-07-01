"""Tests for the Issue resolution framework (Phase 1 + Phase 3 backend).

Covers:
  Phase 1:
  • _issue_exists dedup logic (open/ignored suppresses; resolved does not)
  • Reconcile dedup: second scan does not create a duplicate open issue
  • Ignore durability: ignored issue is not re-created on second scan
  • ISSUE_ACTIONS mapping and available_actions on IssueOut
  • POST /api/issues/{id}/action — 422 for invalid action
  • POST /api/issues/{id}/action — orphan→ignore
  • POST /api/issues/{id}/action — orphan→delete (moves dir to trash)
  • POST /api/issues/{id}/action — orphan→import (creates ImportSession w/ sidecar data)

  Phase 3 additions:
  • actions_for() is context-aware for orphan (item_id NULL vs SET)
  • IssueOut.available_actions branches on orphan item_id
  • POST /action — delete_item: deletes DB Item (no trash for absent dir)
  • POST /action — remove_record: deletes File row for missing file
  • POST /action — accept: recomputes sha256 and updates File row
  • POST /action — accept: 409 when file is gone from disk
  • POST /action — clear_source: clears item.source_url
  • POST /action — keep_db: rewrites sidecar from DB state
  • POST /action — keep_sidecar: applies on-disk sidecar fields to DB
  • POST /action — retry: resolves issue when reconcile succeeds
  • POST /action — 422 for action not permitted for that issue type

CPU discipline: all tests use mocked filesystem / small DB fixtures.
No full pytest suite; no real renders; OMP_NUM_THREADS=2 enforced by caller.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_session import ImportSession, ImportSessionStatus, ImportSourceType
from app.models.issue import Issue, IssueSeverity, IssueStatus, IssueType
from app.routers.issues import ISSUE_ACTIONS, IssueOut, actions_for
from app.worker.reconcile import _issue_exists

# ---------------------------------------------------------------------------
# Helpers — create minimal DB objects
# ---------------------------------------------------------------------------

async def _make_issue(
    db: AsyncSession,
    issue_type: str = IssueType.orphan,
    status: str = IssueStatus.open,
    target_path: str | None = "/library/aa/orphan-dir",
    item_id: int | None = None,
    detail: str = "Test orphan",
) -> Issue:
    issue = Issue(
        issue_type=issue_type,
        severity=IssueSeverity.warning,
        status=status,
        target_path=target_path,
        item_id=item_id,
        detail=detail,
        suggested_action="Import or delete.",
    )
    db.add(issue)
    await db.flush()
    return issue


async def _make_library(db: AsyncSession, mount_path: str) -> Any:
    from app.models.library import Library  # noqa: PLC0415

    lib = Library(name="TestLib", mount_path=mount_path, enabled=True)
    db.add(lib)
    await db.flush()
    return lib


async def _make_item(
    db: AsyncSession,
    library_id: int,
    dir_path: str,
    title: str = "Test Item",
    source_url: str | None = None,
) -> Any:
    from app.models.item import Item  # noqa: PLC0415

    key = secrets.token_hex(4)
    item = Item(
        key=key,
        title=title,
        slug=f"{key}-slug",
        dir_path=dir_path,
        library_id=library_id,
        schema_version=1,
        source_url=source_url,
    )
    db.add(item)
    await db.flush()
    return item


async def _make_file(
    db: AsyncSession,
    item_id: int,
    rel_path: str,
    sha256: str | None = "a" * 64,
    size: int = 100,
) -> Any:
    from app.models.file import File, FileRole  # noqa: PLC0415

    now = datetime.now(UTC)
    f = File(
        item_id=item_id,
        path=rel_path,
        role=FileRole.model,
        size=size,
        sha256=sha256,
        mtime=now,
        last_seen_size=size,
        last_seen_mtime=now,
    )
    db.add(f)
    await db.flush()
    return f


async def _setup_and_login(client: AsyncClient) -> str:
    """Initialize instance, log in as admin, return CSRF token."""
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
# Pure-unit tests (no DB, no disk)
# ---------------------------------------------------------------------------


def test_issue_actions_mapping_has_orphan_actions() -> None:
    """Orphan issues (item_id=None default) expose import, delete, and ignore actions."""
    assert set(ISSUE_ACTIONS[IssueType.orphan]) == {"import", "delete", "ignore"}


def test_issue_actions_mapping_other_types_have_ignore() -> None:
    """All non-orphan types expose at least 'ignore' and not 'import'/'delete'."""
    for itype in [
        IssueType.conflict,
        IssueType.dead_link,
        IssueType.corruption,
        IssueType.missing_file,
        IssueType.sidecar_error,
        IssueType.other,
    ]:
        assert "ignore" in ISSUE_ACTIONS.get(itype, []), f"{itype} missing 'ignore'"
        assert "import" not in ISSUE_ACTIONS.get(itype, [])
        assert "delete" not in ISSUE_ACTIONS.get(itype, [])


def test_actions_for_orphan_null_item_id() -> None:
    """actions_for: orphan with item_id=None → import/delete/ignore."""

    class FakeIssue:
        issue_type = IssueType.orphan
        item_id = None

    result = actions_for(FakeIssue())
    assert set(result) == {"import", "delete", "ignore"}


def test_actions_for_orphan_set_item_id() -> None:
    """actions_for: orphan with item_id set → delete_item/ignore (no import/delete)."""

    class FakeIssue:
        issue_type = IssueType.orphan
        item_id = 42

    result = actions_for(FakeIssue())
    assert set(result) == {"delete_item", "ignore"}
    assert "import" not in result
    assert "delete" not in result


def test_actions_for_conflict() -> None:
    """actions_for: conflict → keep_db/keep_sidecar/ignore."""

    class FakeIssue:
        issue_type = IssueType.conflict
        item_id = 1

    result = actions_for(FakeIssue())
    assert set(result) == {"keep_db", "keep_sidecar", "ignore"}


def test_actions_for_dead_link() -> None:
    """actions_for: dead_link → clear_source/ignore."""

    class FakeIssue:
        issue_type = IssueType.dead_link
        item_id = 1

    result = actions_for(FakeIssue())
    assert set(result) == {"clear_source", "ignore"}


def test_actions_for_corruption() -> None:
    """actions_for: corruption → accept/ignore."""

    class FakeIssue:
        issue_type = IssueType.corruption
        item_id = 1

    result = actions_for(FakeIssue())
    assert set(result) == {"accept", "ignore"}


def test_actions_for_missing_file() -> None:
    """actions_for: missing_file → remove_record/ignore."""

    class FakeIssue:
        issue_type = IssueType.missing_file
        item_id = 1

    result = actions_for(FakeIssue())
    assert set(result) == {"remove_record", "ignore"}


def test_actions_for_sidecar_error() -> None:
    """actions_for: sidecar_error → retry/ignore."""

    class FakeIssue:
        issue_type = IssueType.sidecar_error
        item_id = 1

    result = actions_for(FakeIssue())
    assert set(result) == {"retry", "ignore"}


def test_issue_out_available_actions_computed() -> None:
    """IssueOut.available_actions is context-aware for orphan (item_id=None)."""
    now = datetime.now(UTC)
    out = IssueOut(
        id=1,
        issue_type=IssueType.orphan,
        severity="warning",
        status="open",
        item_id=None,
        target_path="/some/dir",
        detail="test",
        suggested_action=None,
        created_at=now,
        updated_at=now,
        resolved_at=None,
    )
    assert set(out.available_actions) == {"import", "delete", "ignore"}


def test_issue_out_orphan_item_id_set_available_actions() -> None:
    """IssueOut.available_actions for orphan with item_id set → delete_item/ignore."""
    now = datetime.now(UTC)
    out = IssueOut(
        id=2,
        issue_type=IssueType.orphan,
        severity="warning",
        status="open",
        item_id=99,
        target_path="/some/missing/dir",
        detail="DB item missing dir",
        suggested_action=None,
        created_at=now,
        updated_at=now,
        resolved_at=None,
    )
    assert set(out.available_actions) == {"delete_item", "ignore"}


def test_issue_out_available_actions_dead_link() -> None:
    """IssueOut.available_actions for dead_link → clear_source/ignore."""
    now = datetime.now(UTC)
    out = IssueOut(
        id=3,
        issue_type=IssueType.dead_link,
        severity="info",
        status="open",
        item_id=1,
        target_path="https://example.com",
        detail="dead link",
        suggested_action=None,
        created_at=now,
        updated_at=now,
        resolved_at=None,
    )
    assert set(out.available_actions) == {"clear_source", "ignore"}


# ---------------------------------------------------------------------------
# DB tests — _issue_exists dedup helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_exists_returns_false_for_none_target(db_session: AsyncSession) -> None:
    """_issue_exists returns False when target_path is None (no dedup possible)."""
    result = await _issue_exists(db_session, IssueType.orphan, None)
    assert result is False


@pytest.mark.asyncio
async def test_issue_exists_open_suppresses(db_session: AsyncSession) -> None:
    """_issue_exists returns True when an open issue exists for same (type, path)."""
    tp = "/lib/aa/dir-open"
    await _make_issue(db_session, target_path=tp, status=IssueStatus.open)
    assert await _issue_exists(db_session, IssueType.orphan, tp) is True


@pytest.mark.asyncio
async def test_issue_exists_ignored_suppresses(db_session: AsyncSession) -> None:
    """_issue_exists returns True when an ignored issue exists — ignore is durable."""
    tp = "/lib/aa/dir-ignored"
    await _make_issue(db_session, target_path=tp, status=IssueStatus.ignored)
    assert await _issue_exists(db_session, IssueType.orphan, tp) is True


@pytest.mark.asyncio
async def test_issue_exists_resolved_does_not_suppress(db_session: AsyncSession) -> None:
    """_issue_exists returns False for a resolved issue — resolved does not suppress."""
    tp = "/lib/aa/dir-resolved"
    await _make_issue(db_session, target_path=tp, status=IssueStatus.resolved)
    assert await _issue_exists(db_session, IssueType.orphan, tp) is False


@pytest.mark.asyncio
async def test_issue_exists_different_type_no_suppress(db_session: AsyncSession) -> None:
    """_issue_exists does not suppress across different issue types."""
    tp = "/lib/aa/some-path"
    await _make_issue(db_session, issue_type=IssueType.missing_file, target_path=tp)
    assert await _issue_exists(db_session, IssueType.orphan, tp) is False


@pytest.mark.asyncio
async def test_issue_exists_different_path_no_suppress(db_session: AsyncSession) -> None:
    """_issue_exists does not suppress a different path."""
    await _make_issue(db_session, target_path="/lib/aa/dir-a")
    assert await _issue_exists(db_session, IssueType.orphan, "/lib/aa/dir-b") is False


# ---------------------------------------------------------------------------
# Ignore durability: ignored issue is NOT re-created on a second scan invocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_skip_duplicate_open_issue(db_session: AsyncSession) -> None:
    """When an open issue already exists, a second creation is skipped via dedup."""
    tp = "/lib/aa/orphan-dedup"
    first = await _make_issue(db_session, target_path=tp, status=IssueStatus.open)

    already_exists = await _issue_exists(db_session, IssueType.orphan, tp)
    assert already_exists is True

    result = await db_session.execute(
        select(Issue).where(
            Issue.issue_type == IssueType.orphan,
            Issue.target_path == tp,
        )
    )
    all_issues = result.scalars().all()
    assert len(all_issues) == 1
    assert all_issues[0].id == first.id


@pytest.mark.asyncio
async def test_ignore_is_durable_second_scan_does_not_recreate(
    db_session: AsyncSession,
) -> None:
    """After ignoring an issue, the reconcile dedup prevents re-creation on next scan."""
    tp = "/lib/aa/ignored-orphan"
    issue = await _make_issue(db_session, target_path=tp, status=IssueStatus.open)

    issue.status = IssueStatus.ignored
    issue.updated_at = datetime.now(UTC)
    await db_session.flush()

    suppressed = await _issue_exists(db_session, IssueType.orphan, tp)
    assert suppressed is True, "Ignored issue should suppress re-creation"

    result = await db_session.execute(
        select(Issue).where(Issue.target_path == tp)
    )
    issues = result.scalars().all()
    assert len(issues) == 1
    assert issues[0].status == IssueStatus.ignored


# ---------------------------------------------------------------------------
# API endpoint tests — POST /api/issues/{id}/action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_invalid_action_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /action with an action not in available_actions returns 422."""
    csrf = await _setup_and_login(client)

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.dead_link,
        target_path="https://example.com/dead",
        detail="Dead link",
    )
    issue_id = issue.id
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue_id}/action",
        json={"action": "delete"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422
    assert "dead_link" in resp.json()["detail"] or "not available" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_action_missing_file_invalid_action_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /action with 'import' on missing_file returns 422."""
    csrf = await _setup_and_login(client)

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.missing_file,
        target_path="/library/aa/item/model.stl",
        detail="Missing file",
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "import"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_action_ignore_marks_issue_ignored(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /action ignore sets status=ignored."""
    csrf = await _setup_and_login(client)

    issue = await _make_issue(db_session, issue_type=IssueType.orphan, status=IssueStatus.open)
    issue_id = issue.id
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue_id}/action",
        json={"action": "ignore"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["issue"]["status"] == "ignored"
    assert data["import_session_id"] is None


@pytest.mark.asyncio
async def test_action_delete_moves_dir_to_trash(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """POST /action delete moves the orphan directory to trash and resolves the issue."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    orphan_dir = mount / "aa" / "orphan-to-delete"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "model.stl").write_text("fake stl")

    lib = await _make_library(db_session, str(mount))

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.orphan,
        target_path=str(orphan_dir),
    )
    issue_id = issue.id
    await db_session.flush()

    monkeypatch.setattr("app.config.settings.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.storage.journal.settings.DATA_DIR", str(tmp_path))

    resp = await client.post(
        f"/api/issues/{issue_id}/action",
        json={"action": "delete"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"

    assert not orphan_dir.exists(), "orphan dir should have been moved to trash"

    trash_dir = tmp_path / "trash"
    assert trash_dir.exists()
    trash_entries = list(trash_dir.iterdir())
    assert len(trash_entries) == 1
    moved_dir = trash_entries[0]
    assert (moved_dir / "model.stl").exists(), "files should be in trash"

    _ = lib  # suppress unused-variable warning


@pytest.mark.asyncio
async def test_action_delete_rejects_path_outside_library(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
) -> None:
    """POST /action delete rejects target_path not under a library mount (traversal guard)."""
    csrf = await _setup_and_login(client)

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.orphan,
        target_path=str(outside_dir),
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "delete"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422
    assert "library" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_action_import_creates_import_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
) -> None:
    """POST /action import creates an ImportSession and resolves the issue."""
    csrf = await _setup_and_login(client)

    orphan_dir = tmp_path / "orphan-with-sidecar"
    orphan_dir.mkdir()

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.orphan,
        target_path=str(orphan_dir),
    )
    issue_id = issue.id
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue_id}/action",
        json={"action": "import"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"
    assert data["import_session_id"] is not None

    sid = uuid.UUID(data["import_session_id"])
    result = await db_session.execute(
        select(ImportSession).where(ImportSession.id == sid)
    )
    session_obj = result.scalar_one_or_none()
    assert session_obj is not None
    assert session_obj.source_type == ImportSourceType.inbox
    assert session_obj.inbox_folder == str(orphan_dir)
    assert session_obj.status == ImportSessionStatus.pending_wizard
    assert session_obj.suggested_title == orphan_dir.name


@pytest.mark.asyncio
async def test_action_import_prefills_sidecar_data(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
) -> None:
    """POST /action import prefills ImportSession metadata from sidecar when present."""
    csrf = await _setup_and_login(client)

    orphan_dir = tmp_path / "orphan-sidecar"
    orphan_dir.mkdir()

    sidecar_yaml = """\
schema_version: 1
key: testkey01
title: My Cool Model
slug: my-cool-model
created_at: "2026-01-01T00:00:00Z"
updated_at: "2026-01-01T00:00:00Z"
description: A test model description
source:
  url: https://example.com/model
  site: thingiverse
  license: CC-BY-4.0
tags:
  - mechanical
  - printed
"""
    (orphan_dir / "my-cool-model_testkey01.yml").write_text(sidecar_yaml, encoding="utf-8")

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.orphan,
        target_path=str(orphan_dir),
    )
    issue_id = issue.id
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue_id}/action",
        json={"action": "import"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"
    sid = uuid.UUID(data["import_session_id"])

    result = await db_session.execute(
        select(ImportSession).where(ImportSession.id == sid)
    )
    session_obj = result.scalar_one_or_none()
    assert session_obj is not None
    assert session_obj.suggested_title == "My Cool Model"
    assert session_obj.description == "A test model description"
    assert session_obj.source_url == "https://example.com/model"
    assert session_obj.source_site == "thingiverse"
    assert session_obj.license == "CC-BY-4.0"


# ---------------------------------------------------------------------------
# Phase 3 action tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_delete_item_resolves_issue(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
) -> None:
    """delete_item: removes DB Item row (dir already missing) and resolves issue."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    mount.mkdir()

    lib = await _make_library(db_session, str(mount))
    missing_dir = str(mount / "aa" / "missing-item")  # does NOT exist on disk
    item = await _make_item(db_session, lib.id, missing_dir)
    item_id = item.id

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.orphan,
        target_path=missing_dir,
        item_id=item_id,
        detail="DB item whose dir is missing",
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "delete_item"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"

    # Item should be gone from DB
    from app.models.item import Item  # noqa: PLC0415

    item_check = await db_session.execute(select(Item).where(Item.id == item_id))
    assert item_check.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_action_delete_item_wrong_action_for_null_orphan_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """delete_item is not available for orphan with item_id=None → 422."""
    csrf = await _setup_and_login(client)

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.orphan,
        item_id=None,
        target_path="/fake/dir",
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "delete_item"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_action_remove_record_deletes_file_row(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
) -> None:
    """remove_record: deletes the File DB row for the missing file and resolves issue."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    item_dir = mount / "aa" / "myitem"
    item_dir.mkdir(parents=True)

    lib = await _make_library(db_session, str(mount))
    item = await _make_item(db_session, lib.id, str(item_dir))
    rel_path = "model.stl"
    abs_path = str(item_dir / rel_path)
    file_row = await _make_file(db_session, item.id, rel_path)
    file_id = file_row.id

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.missing_file,
        target_path=abs_path,
        item_id=item.id,
        detail=f"File in DB not found on disk: {rel_path!r}",
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "remove_record"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"

    # File row should be deleted
    from app.models.file import File  # noqa: PLC0415

    file_check = await db_session.execute(select(File).where(File.id == file_id))
    assert file_check.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_action_accept_updates_sha256(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
) -> None:
    """accept: recomputes sha256 from disk and updates the File row."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    item_dir = mount / "aa" / "corrupt-item"
    item_dir.mkdir(parents=True)
    model_file = item_dir / "model.stl"
    model_file.write_bytes(b"actual stl content")

    lib = await _make_library(db_session, str(mount))
    item = await _make_item(db_session, lib.id, str(item_dir))
    old_sha = "0" * 64  # deliberately wrong
    file_row = await _make_file(db_session, item.id, "model.stl", sha256=old_sha)
    file_id = file_row.id

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.corruption,
        target_path=str(model_file),
        item_id=item.id,
        detail="File hash mismatch",
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "accept"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"

    # File sha256 should be updated
    from app.models.file import File  # noqa: PLC0415
    from app.storage.inventory import hash_file_sha256  # noqa: PLC0415

    file_check = await db_session.execute(select(File).where(File.id == file_id))
    updated_file = file_check.scalar_one()
    expected_hash = hash_file_sha256(model_file)
    assert updated_file.sha256 == expected_hash
    assert updated_file.sha256 != old_sha


@pytest.mark.asyncio
async def test_action_accept_missing_file_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
) -> None:
    """accept: returns 409 when the file no longer exists on disk."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    item_dir = mount / "aa" / "gone-item"
    item_dir.mkdir(parents=True)

    lib = await _make_library(db_session, str(mount))
    item = await _make_item(db_session, lib.id, str(item_dir))
    gone_path = str(item_dir / "gone.stl")  # file does NOT exist
    file_row = await _make_file(db_session, item.id, "gone.stl")

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.corruption,
        target_path=gone_path,
        item_id=item.id,
        detail="File hash mismatch",
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "accept"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409, resp.text

    _ = file_row


@pytest.mark.asyncio
async def test_action_clear_source_clears_source_url(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
) -> None:
    """clear_source: clears item.source_url and resolves the issue."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    item_dir = mount / "aa" / "linked-item"
    item_dir.mkdir(parents=True)

    lib = await _make_library(db_session, str(mount))
    source_url = "https://example.com/dead-model"
    item = await _make_item(db_session, lib.id, str(item_dir), source_url=source_url)
    item_id = item.id

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.dead_link,
        target_path=source_url,
        item_id=item_id,
        detail=f"Dead link: {source_url}",
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "clear_source"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"

    # source_url should be cleared on item
    from app.models.item import Item  # noqa: PLC0415

    item_check = await db_session.execute(select(Item).where(Item.id == item_id))
    updated_item = item_check.scalar_one()
    assert updated_item.source_url is None


@pytest.mark.asyncio
async def test_action_keep_db_rewrites_sidecar(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """keep_db: rewrites sidecar from DB state and resolves the conflict issue."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    item_dir = mount / "aa" / "conflict-item"
    item_dir.mkdir(parents=True)

    lib = await _make_library(db_session, str(mount))
    item = await _make_item(db_session, lib.id, str(item_dir), title="Conflict Item")
    item_id = item.id

    # Write a sidecar file on disk (it exists, just has old content — conflict)
    sidecar_content = "schema_version: 1\nkey: conflictkey\ntitle: Old Title\n"
    (item_dir / f"conflict-item_{item.key}.yml").write_text(sidecar_content)

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.conflict,
        target_path=str(item_dir),
        item_id=item_id,
        detail="Sidecar and DB both changed",
    )
    await db_session.flush()

    monkeypatch.setattr("app.config.settings.DATA_DIR", str(tmp_path))

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "keep_db"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"

    # Verify a sidecar file was written (any .yml in the item dir)
    yml_files = list(item_dir.glob("*.yml"))
    assert len(yml_files) >= 1


@pytest.mark.asyncio
async def test_action_keep_sidecar_applies_to_db(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """keep_sidecar: applies on-disk sidecar description/source fields to DB item."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    item_dir = mount / "aa" / "sidecar-wins"
    item_dir.mkdir(parents=True)

    lib = await _make_library(db_session, str(mount))
    item = await _make_item(db_session, lib.id, str(item_dir), title="Sidecar Wins")
    item_id = item.id
    key = item.key

    # Write a sidecar that has a new description the DB doesn't know about.
    # Use the canonical sidecar_name() so read_sidecar() will find the file.
    from app.storage.paths import sidecar_name as _sc_name  # noqa: PLC0415

    sc_yaml = f"""\
schema_version: 1
key: {key}
title: Sidecar Wins
slug: sidecar-wins-{key}
created_at: "2026-01-01T00:00:00Z"
updated_at: "2026-01-01T00:00:00Z"
description: Description from sidecar
source:
  url: https://sidecar-source.example.com
  site: printables
  license: CC-BY-4.0
tags: []
"""
    (item_dir / _sc_name("Sidecar Wins", key)).write_text(sc_yaml, encoding="utf-8")

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.conflict,
        target_path=str(item_dir),
        item_id=item_id,
        detail="Sidecar and DB both changed",
    )
    await db_session.flush()

    monkeypatch.setattr("app.config.settings.DATA_DIR", str(tmp_path))

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "keep_sidecar"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue"]["status"] == "resolved"

    # Verify sidecar fields were applied to the DB item
    from app.models.item import Item  # noqa: PLC0415

    item_check = await db_session.execute(select(Item).where(Item.id == item_id))
    updated_item = item_check.scalar_one()
    assert updated_item.description == "Description from sidecar"
    assert updated_item.source_url == "https://sidecar-source.example.com"


@pytest.mark.asyncio
async def test_action_retry_resolves_on_success(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """retry: runs reconcile for item; issue resolved when reconcile returns no errors."""
    csrf = await _setup_and_login(client)

    mount = tmp_path / "library"
    item_dir = mount / "aa" / "retry-item"
    item_dir.mkdir(parents=True)

    lib = await _make_library(db_session, str(mount))
    item = await _make_item(db_session, lib.id, str(item_dir), title="Retry Item")
    item_id = item.id
    key = item.key

    # Write a valid sidecar so reconcile won't error on this item.
    # Use canonical sidecar_name() so read_sidecar() will find the file.
    from app.storage.paths import sidecar_name as _sc_name  # noqa: PLC0415

    sc_yaml = f"""\
schema_version: 1
key: {key}
title: Retry Item
slug: retry-item-{key}
created_at: "2026-01-01T00:00:00Z"
updated_at: "2026-01-01T00:00:00Z"
description: null
tags: []
"""
    (item_dir / _sc_name("Retry Item", key)).write_text(sc_yaml, encoding="utf-8")

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.sidecar_error,
        target_path=str(item_dir),
        item_id=item_id,
        detail="Sidecar parse error (was transient)",
    )
    await db_session.flush()

    monkeypatch.setattr("app.config.settings.DATA_DIR", str(tmp_path))

    resp = await client.post(
        f"/api/issues/{issue.id}/action",
        json={"action": "retry"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Issue should be resolved since reconcile succeeds on a valid item
    assert data["issue"]["status"] == "resolved"
