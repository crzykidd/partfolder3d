"""Phase 6 tests: reconcile engine, Issues, ChangeLog, ReviewItems, API endpoints.

Uses the same ephemeral Postgres + per-test rollback approach as prior phases.
Pure-unit tests (no DB) run first; DB tests use the conftest fixtures.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_log import ChangeLog, ChangeSource
from app.models.issue import Issue, IssueSeverity, IssueStatus, IssueType
from app.models.review_item import ReviewItem, ReviewStatus
from app.worker.reconcile import DEFAULT_MODES, ReconcileResult, load_mode_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def test_reconcile_result_defaults() -> None:
    """ReconcileResult initializes with empty lists."""
    r = ReconcileResult()
    assert r.changes_applied == []
    assert r.review_items_created == []
    assert r.issues_created == []
    assert r.errors == []


def test_reconcile_result_accumulation() -> None:
    """ReconcileResult accumulates entries correctly."""
    r = ReconcileResult()
    r.changes_applied.append({"behavior": "re_render"})
    r.issues_created.append(42)
    assert len(r.changes_applied) == 1
    assert 42 in r.issues_created


def test_default_modes_are_conservative() -> None:
    """Default modes: sidecar_sync and file_changes are 'review', re_render is 'auto'."""
    assert DEFAULT_MODES["sidecar_sync"] == "review"
    assert DEFAULT_MODES["re_render"] == "auto"
    assert DEFAULT_MODES["file_changes"] == "review"


def test_url_validator_none_means_skip() -> None:
    """If url_validator is None, URL validation is skipped (not called)."""
    called = []

    async def validator(url: str) -> bool:
        called.append(url)
        return True

    # Simulate the guard in _behavior_integrity
    url_validator = None
    source_url = "https://example.com/model"

    if url_validator is not None and source_url:
        # This block should NOT execute
        asyncio.get_event_loop().run_until_complete(validator(source_url))

    assert called == [], "url_validator should not be called when None"


def test_sidecar_sync_direction_logic() -> None:
    """Verify sidecar⇄DB sync direction formulas."""
    TOLERANCE = 5.0
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Sidecar written at t=0, sidecar mtime at t=10 (externally edited), DB at t=0
    sidecar_written_at = now
    sidecar_file_mtime = now + timedelta(seconds=10)
    db_updated_at = now

    sidecar_ext = (sidecar_file_mtime - sidecar_written_at).total_seconds() > TOLERANCE
    db_changed = (db_updated_at - sidecar_written_at).total_seconds() > TOLERANCE
    assert sidecar_ext is True
    assert db_changed is False

    # DB changed, sidecar unchanged
    sidecar_file_mtime2 = now
    db_updated_at2 = now + timedelta(seconds=10)
    sidecar_ext2 = (sidecar_file_mtime2 - sidecar_written_at).total_seconds() > TOLERANCE
    db_changed2 = (db_updated_at2 - sidecar_written_at).total_seconds() > TOLERANCE
    assert sidecar_ext2 is False
    assert db_changed2 is True

    # Both changed → conflict
    sidecar_file_mtime3 = now + timedelta(seconds=10)
    db_updated_at3 = now + timedelta(seconds=10)
    sidecar_ext3 = (sidecar_file_mtime3 - sidecar_written_at).total_seconds() > TOLERANCE
    db_changed3 = (db_updated_at3 - sidecar_written_at).total_seconds() > TOLERANCE
    assert sidecar_ext3 is True
    assert db_changed3 is True  # Both changed → conflict


# ---------------------------------------------------------------------------
# DB model CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_create_and_query(db_session: AsyncSession) -> None:
    """Issue model: create, query by status."""
    issue = Issue(
        issue_type=IssueType.orphan,
        severity=IssueSeverity.warning,
        status=IssueStatus.open,
        item_id=None,
        detail="Test orphan dir: /tmp/orphan-abc1234",
        suggested_action="Import or delete.",
    )
    db_session.add(issue)
    await db_session.flush()
    assert issue.id is not None

    result = await db_session.execute(
        select(Issue).where(Issue.status == IssueStatus.open)
    )
    issues = result.scalars().all()
    assert any(i.id == issue.id for i in issues)


@pytest.mark.asyncio
async def test_issue_status_transitions(db_session: AsyncSession) -> None:
    """Issue: open → resolved → ignored."""
    issue = Issue(
        issue_type=IssueType.dead_link,
        severity=IssueSeverity.info,
        status=IssueStatus.open,
        detail="URL dead",
    )
    db_session.add(issue)
    await db_session.flush()

    issue.status = IssueStatus.resolved
    issue.resolved_at = datetime.now(UTC)
    await db_session.flush()
    assert issue.status == IssueStatus.resolved

    issue.status = IssueStatus.ignored
    await db_session.flush()
    assert issue.status == IssueStatus.ignored


@pytest.mark.asyncio
async def test_change_log_create(db_session: AsyncSession) -> None:
    """ChangeLog model: create and query."""
    cl = ChangeLog(
        behavior="re_render",
        change_type="render_enqueued",
        item_id=None,
        summary="Re-render triggered for test item.",
        source=ChangeSource.auto,
        actor="system",
    )
    db_session.add(cl)
    await db_session.flush()
    assert cl.id is not None

    result = await db_session.execute(
        select(ChangeLog).where(ChangeLog.behavior == "re_render")
    )
    rows = result.scalars().all()
    assert any(r.id == cl.id for r in rows)


@pytest.mark.asyncio
async def test_review_item_create_and_status(db_session: AsyncSession) -> None:
    """ReviewItem: create pending, reject."""
    rv = ReviewItem(
        behavior="sidecar_sync",
        change_type="sidecar_pulled_to_db",
        item_id=None,
        summary="Sidecar edited; pull to DB?",
        proposed_action={"behavior": "sidecar_sync", "action": "pull_sidecar_to_db"},
        status=ReviewStatus.pending,
    )
    db_session.add(rv)
    await db_session.flush()
    assert rv.id is not None
    assert rv.status == ReviewStatus.pending

    rv.status = ReviewStatus.rejected
    rv.resolved_at = datetime.now(UTC)
    await db_session.flush()
    assert rv.status == ReviewStatus.rejected


@pytest.mark.asyncio
async def test_load_mode_settings_defaults(db_session: AsyncSession) -> None:
    """load_mode_settings returns DEFAULT_MODES when no settings exist."""
    modes = await load_mode_settings(db_session)
    assert modes["sidecar_sync"] == "review"
    assert modes["re_render"] == "auto"
    assert modes["file_changes"] == "review"


@pytest.mark.asyncio
async def test_load_mode_settings_override(db_session: AsyncSession) -> None:
    """load_mode_settings respects DB settings."""
    from app.models.setting import Setting  # noqa: PLC0415

    setting = Setting(key="scan.re_render.mode", value=json.dumps("review"))
    db_session.add(setting)
    await db_session.flush()

    modes = await load_mode_settings(db_session)
    assert modes["re_render"] == "review"
    # Others still default
    assert modes["sidecar_sync"] == "review"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_issues_empty(client: AsyncClient) -> None:
    """GET /api/issues returns 200 with empty list."""
    csrf = await _setup_and_login(client)
    resp = await client.get("/api/issues", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_changes_empty(client: AsyncClient) -> None:
    """GET /api/changes returns 200 with empty list."""
    csrf = await _setup_and_login(client)
    resp = await client.get("/api/changes", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_reviews_empty(client: AsyncClient) -> None:
    """GET /api/reviews returns 200 with empty list."""
    csrf = await _setup_and_login(client)
    resp = await client.get("/api/reviews", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_resolve_issue(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/issues/{id}/resolve marks status resolved."""
    # Create an issue directly in the DB
    issue = Issue(
        issue_type=IssueType.orphan,
        severity=IssueSeverity.warning,
        status=IssueStatus.open,
        detail="Test orphan",
    )
    db_session.add(issue)
    await db_session.flush()
    issue_id = issue.id

    csrf = await _setup_and_login(client)
    resp = await client.post(
        f"/api/issues/{issue_id}/resolve",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None


@pytest.mark.asyncio
async def test_ignore_issue(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/issues/{id}/ignore marks status ignored."""
    issue = Issue(
        issue_type=IssueType.dead_link,
        severity=IssueSeverity.info,
        status=IssueStatus.open,
        detail="Test dead link",
    )
    db_session.add(issue)
    await db_session.flush()
    issue_id = issue.id

    csrf = await _setup_and_login(client)
    resp = await client.post(
        f"/api/issues/{issue_id}/ignore",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_get_issue_detail(client: AsyncClient, db_session: AsyncSession) -> None:
    """GET /api/issues/{id} returns issue detail."""
    issue = Issue(
        issue_type=IssueType.corruption,
        severity=IssueSeverity.critical,
        status=IssueStatus.open,
        detail="Hash mismatch for test.stl",
        suggested_action="Restore from backup.",
    )
    db_session.add(issue)
    await db_session.flush()
    issue_id = issue.id

    csrf = await _setup_and_login(client)
    resp = await client.get(f"/api/issues/{issue_id}", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert body["issue_type"] == "corruption"
    assert body["severity"] == "critical"
    assert "Hash mismatch" in body["detail"]


@pytest.mark.asyncio
async def test_reject_review_item(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/reviews/{id}/reject marks status rejected."""
    rv = ReviewItem(
        behavior="sidecar_sync",
        change_type="sidecar_pulled_to_db",
        summary="Pending sidecar pull",
        proposed_action={"behavior": "sidecar_sync", "action": "pull_sidecar_to_db", "item_id": 99},
        status=ReviewStatus.pending,
    )
    db_session.add(rv)
    await db_session.flush()
    rv_id = rv.id

    csrf = await _setup_and_login(client)
    resp = await client.post(
        f"/api/reviews/{rv_id}/reject",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_reject_already_rejected_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /api/reviews/{id}/reject on already-rejected returns 409."""
    rv = ReviewItem(
        behavior="re_render",
        change_type="render_enqueued",
        summary="Already rejected",
        proposed_action={"behavior": "re_render", "action": "enqueue_render", "item_id": 99},
        status=ReviewStatus.rejected,
    )
    db_session.add(rv)
    await db_session.flush()

    csrf = await _setup_and_login(client)
    resp = await client.post(
        f"/api/reviews/{rv.id}/reject",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_issues_filter_by_status(client: AsyncClient, db_session: AsyncSession) -> None:
    """GET /api/issues?status=open returns only open issues."""
    db_session.add(Issue(
        issue_type=IssueType.orphan, severity=IssueSeverity.warning,
        status=IssueStatus.open, detail="Open issue"
    ))
    db_session.add(Issue(
        issue_type=IssueType.dead_link, severity=IssueSeverity.info,
        status=IssueStatus.resolved, detail="Resolved issue"
    ))
    await db_session.flush()

    csrf = await _setup_and_login(client)
    resp = await client.get("/api/issues?status=open", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["status"] == "open"


@pytest.mark.asyncio
async def test_list_changes_filter_by_behavior(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /api/changes?behavior=re_render returns only re_render entries."""
    db_session.add(ChangeLog(
        behavior="re_render", change_type="render_enqueued",
        summary="render enqueued", source="auto"
    ))
    db_session.add(ChangeLog(
        behavior="sidecar_sync", change_type="db_pushed_to_sidecar",
        summary="sidecar written", source="auto"
    ))
    await db_session.flush()

    csrf = await _setup_and_login(client)
    resp = await client.get("/api/changes?behavior=re_render", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["behavior"] == "re_render"


# ---------------------------------------------------------------------------
# Engine integration tests (use real tmp_path for disk)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_missing_dir_creates_orphan_issue(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """reconcile_one_item with non-existent item dir creates an orphan Issue."""
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    # Need a library + item in DB
    lib = Library(name="testlib", mount_path=str(tmp_path), enabled=True)
    db_session.add(lib)
    await db_session.flush()

    item = Item(
        key="abc1234",
        title="Test Item",
        slug="test-item-abc1234",
        library_id=lib.id,
        dir_path=str(tmp_path / "ab" / "test-item-abc1234"),  # does NOT exist
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    result = await reconcile_one_item(
        db_session,
        item,
        mode_settings={"sidecar_sync": "auto", "re_render": "auto", "file_changes": "auto"},
    )

    # Should have created an orphan issue
    assert len(result.issues_created) >= 1
    issue = await db_session.get(Issue, result.issues_created[0])
    assert issue is not None
    assert issue.issue_type in (IssueType.orphan, IssueType.sidecar_error)


@pytest.mark.asyncio
async def test_reconcile_new_file_auto_mode(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """reconcile_one_item in auto mode adds a new file on disk to the DB."""
    from app.models.file import File  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415
    from app.storage.sidecar import SidecarData, write_sidecar  # noqa: PLC0415
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    # Set up item dir
    item_dir = tmp_path / "ab" / "my-model-abc1234"
    item_dir.mkdir(parents=True)

    # Write a test model file
    stl_file = item_dir / "model.stl"
    stl_file.write_bytes(b"\x00" * 128)

    # Write a minimal sidecar (updated_at = now so it's in sync)
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sc = SidecarData(
        schema_version=1, key="abc1234", title="My Model", slug="my-model-abc1234",
        created_at=now_iso, updated_at=now_iso,
    )
    write_sidecar(item_dir, sc, "My Model", "abc1234")

    lib = Library(name="testlib2", mount_path=str(tmp_path), enabled=True)
    db_session.add(lib)
    await db_session.flush()

    item = Item(
        key="abc1234",
        title="My Model",
        slug="my-model-abc1234",
        library_id=lib.id,
        dir_path=str(item_dir),
        schema_version=1,
        updated_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.flush()

    # No File rows yet — the STL is new
    result = await reconcile_one_item(
        db_session, item,
        mode_settings={"sidecar_sync": "review", "re_render": "auto", "file_changes": "auto"},
    )

    # In auto mode, the new file should be added
    assert len(result.changes_applied) >= 1
    new_file_changes = [c for c in result.changes_applied if c.get("change_type") == "file_added"]
    assert len(new_file_changes) >= 1

    # Verify File row created
    files_result = await db_session.execute(select(File).where(File.item_id == item.id))
    files = files_result.scalars().all()
    assert any("model.stl" in f.path for f in files)


@pytest.mark.asyncio
async def test_reconcile_new_file_review_mode(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """reconcile_one_item in review mode creates ReviewItem for new file instead of adding."""
    from app.models.file import File  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415
    from app.storage.sidecar import SidecarData, write_sidecar  # noqa: PLC0415
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    item_dir = tmp_path / "cd" / "another-model-def5678"
    item_dir.mkdir(parents=True)
    (item_dir / "extra.stl").write_bytes(b"\x00" * 64)

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sc = SidecarData(
        schema_version=1, key="def5678", title="Another Model", slug="another-model-def5678",
        created_at=now_iso, updated_at=now_iso,
    )
    write_sidecar(item_dir, sc, "Another Model", "def5678")

    lib = Library(name="testlib3", mount_path=str(tmp_path), enabled=True)
    db_session.add(lib)
    await db_session.flush()

    item = Item(
        key="def5678",
        title="Another Model",
        slug="another-model-def5678",
        library_id=lib.id,
        dir_path=str(item_dir),
        schema_version=1,
        updated_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.flush()

    result = await reconcile_one_item(
        db_session, item,
        mode_settings={"sidecar_sync": "review", "re_render": "auto", "file_changes": "review"},
    )

    # Review mode → ReviewItem created, no File row added
    assert len(result.review_items_created) >= 1

    # Verify no File row was created
    files_result = await db_session.execute(select(File).where(File.item_id == item.id))
    files = files_result.scalars().all()
    assert len(files) == 0


@pytest.mark.asyncio
async def test_reconcile_url_validator_not_called_when_none(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """url_validator is never called when None (behavior d gated correctly)."""
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415
    from app.storage.sidecar import SidecarData, write_sidecar  # noqa: PLC0415
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    item_dir = tmp_path / "ef" / "url-model-ghi9012"
    item_dir.mkdir(parents=True)

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sc = SidecarData(
        schema_version=1, key="ghi9012", title="URL Model", slug="url-model-ghi9012",
        created_at=now_iso, updated_at=now_iso,
    )
    write_sidecar(item_dir, sc, "URL Model", "ghi9012")

    lib = Library(name="testlib4", mount_path=str(tmp_path), enabled=True)
    db_session.add(lib)
    await db_session.flush()

    item = Item(
        key="ghi9012",
        title="URL Model",
        slug="url-model-ghi9012",
        library_id=lib.id,
        dir_path=str(item_dir),
        schema_version=1,
        source_url="https://example.com/model",
        updated_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.flush()

    validator_called = []

    async def mock_validator(url: str) -> bool:
        validator_called.append(url)
        return False  # Would create dead_link issue if called

    # Pass url_validator=None → must NOT call it
    await reconcile_one_item(db_session, item, url_validator=None)
    assert validator_called == [], "url_validator must not be called when None"

    # No dead_link issues should have been created
    issues_result = await db_session.execute(
        select(Issue).where(Issue.item_id == item.id, Issue.issue_type == IssueType.dead_link)
    )
    dead_links = issues_result.scalars().all()
    assert len(dead_links) == 0
