"""Tests for the Issue resolution framework (Phase 1 backend).

Covers:
  • _issue_exists dedup logic (open/ignored suppresses; resolved does not)
  • Reconcile dedup: second scan does not create a duplicate open issue
  • Ignore durability: ignored issue is not re-created on second scan
  • ISSUE_ACTIONS mapping and available_actions on IssueOut
  • POST /api/issues/{id}/action — 422 for invalid action
  • POST /api/issues/{id}/action — orphan→ignore
  • POST /api/issues/{id}/action — orphan→delete (moves dir to trash)
  • POST /api/issues/{id}/action — orphan→import (creates ImportSession w/ sidecar data)

CPU discipline: all tests use mocked filesystem / small DB fixtures.
No full pytest suite; no real renders; OMP_NUM_THREADS=2 enforced by caller.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_session import ImportSession, ImportSessionStatus, ImportSourceType
from app.models.issue import Issue, IssueSeverity, IssueStatus, IssueType
from app.routers.issues import ISSUE_ACTIONS, IssueOut
from app.worker.reconcile import _issue_exists

# ---------------------------------------------------------------------------
# Helper — create a minimal Issue in the DB
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
    """Orphan issues expose import, delete, and ignore actions."""
    assert set(ISSUE_ACTIONS[IssueType.orphan]) == {"import", "delete", "ignore"}


def test_issue_actions_mapping_other_types_have_ignore() -> None:
    """All non-orphan types expose at least 'ignore'."""
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


def test_issue_out_available_actions_computed() -> None:
    """IssueOut.available_actions is computed from issue_type via model_validator."""
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


def test_issue_out_available_actions_other_type() -> None:
    """IssueOut.available_actions = ['ignore'] for non-orphan types."""
    now = datetime.now(UTC)
    out = IssueOut(
        id=2,
        issue_type=IssueType.dead_link,
        severity="info",
        status="open",
        item_id=None,
        target_path="https://example.com",
        detail="dead link",
        suggested_action=None,
        created_at=now,
        updated_at=now,
        resolved_at=None,
    )
    assert out.available_actions == ["ignore"]


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
    # orphan check should still return False — different type
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

    # Simulate second scan: check dedup, do NOT create if exists
    already_exists = await _issue_exists(db_session, IssueType.orphan, tp)
    assert already_exists is True

    # Verify no second issue was created
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

    # User ignores the issue
    issue.status = IssueStatus.ignored
    issue.updated_at = datetime.now(UTC)
    await db_session.flush()

    # Second scan dedup check
    suppressed = await _issue_exists(db_session, IssueType.orphan, tp)
    assert suppressed is True, "Ignored issue should suppress re-creation"

    # Simulate scan not creating a new issue
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

    # Create a dead_link issue in the test DB session (same session the client uses
    # via the dependency override in the conftest client fixture).
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

    # Create a fake library + fake orphan dir
    from app.models.library import Library  # noqa: PLC0415

    mount = tmp_path / "library"
    orphan_dir = mount / "aa" / "orphan-to-delete"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "model.stl").write_text("fake stl")

    lib = Library(name="TestLib", mount_path=str(mount), enabled=True)
    db_session.add(lib)
    await db_session.flush()

    issue = await _make_issue(
        db_session,
        issue_type=IssueType.orphan,
        target_path=str(orphan_dir),
    )
    issue_id = issue.id
    await db_session.flush()

    # Patch DATA_DIR so trash goes into tmp_path
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

    # Orphan dir should no longer exist at original path
    assert not orphan_dir.exists(), "orphan dir should have been moved to trash"

    # Trash dir should contain the moved dir
    trash_dir = tmp_path / "trash"
    assert trash_dir.exists()
    trash_entries = list(trash_dir.iterdir())
    assert len(trash_entries) == 1
    moved_dir = trash_entries[0]
    assert (moved_dir / "model.stl").exists(), "files should be in trash"


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
    # No library exists so the path is outside all library mounts → 422
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

    # Verify ImportSession was created in the DB
    sid = uuid.UUID(data["import_session_id"])
    result = await db_session.execute(
        select(ImportSession).where(ImportSession.id == sid)
    )
    session_obj = result.scalar_one_or_none()
    assert session_obj is not None
    assert session_obj.source_type == ImportSourceType.inbox
    assert session_obj.inbox_folder == str(orphan_dir)
    assert session_obj.status == ImportSessionStatus.pending_wizard
    # Title defaults to the directory name when no sidecar
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

    # Write a minimal valid sidecar YAML into the orphan dir
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

    # Sidecar fields should be prefilled
    assert session_obj.suggested_title == "My Cool Model"
    assert session_obj.description == "A test model description"
    assert session_obj.source_url == "https://example.com/model"
    assert session_obj.source_site == "thingiverse"
    assert session_obj.license == "CC-BY-4.0"
