"""Phase 6 tests: reconcile engine, Issues, ChangeLog, ReviewItems, API endpoints.

Uses the same ephemeral Postgres + per-test rollback approach as prior phases.
Pure-unit tests (no DB) run first; DB tests use the conftest fixtures.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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


# ---------------------------------------------------------------------------
# Reviews — bulk approve-all / reject-all (2026-07-23-reviews-bulk-approve-reject)
# ---------------------------------------------------------------------------


async def _make_review(
    db_session: AsyncSession,
    *,
    status: str = ReviewStatus.pending,
    item_id: int = 1,
) -> ReviewItem:
    rv = ReviewItem(
        behavior="sidecar_sync",
        change_type="sidecar_pulled_to_db",
        summary="Pending sidecar pull",
        proposed_action={
            "behavior": "sidecar_sync",
            "action": "pull_sidecar_to_db",
            "item_id": item_id,
        },
        status=status,
    )
    db_session.add(rv)
    await db_session.flush()
    return rv


@pytest.mark.asyncio
async def test_reviews_approve_all(
    client: AsyncClient, db_session: AsyncSession, arq_pool: Any
) -> None:
    """POST /api/reviews/approve-all approves every pending item and enqueues one
    apply_review_item job per item; already-resolved items are left untouched."""
    rv1 = await _make_review(db_session, item_id=1)
    rv2 = await _make_review(db_session, item_id=2)
    already_rejected = await _make_review(db_session, status=ReviewStatus.rejected, item_id=3)

    csrf = await _setup_and_login(client)
    resp = await client.post("/api/reviews/approve-all", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    assert resp.json()["approved"] == 2

    result = await db_session.execute(
        select(ReviewItem).where(ReviewItem.status == ReviewStatus.pending)
    )
    assert result.scalars().all() == []

    for rv in (rv1, rv2):
        await db_session.refresh(rv)
        assert rv.status == ReviewStatus.approved
        assert rv.resolved_at is not None
        assert rv.resolved_by_id is not None

    await db_session.refresh(already_rejected)
    assert already_rejected.status == ReviewStatus.rejected

    assert arq_pool.enqueue_job.await_count == 2
    enqueued_ids = {call.args[1] for call in arq_pool.enqueue_job.await_args_list}
    assert enqueued_ids == {rv1.id, rv2.id}
    for call in arq_pool.enqueue_job.await_args_list:
        assert call.args[0] == "apply_review_item"


@pytest.mark.asyncio
async def test_reviews_approve_all_idempotent(
    client: AsyncClient, db_session: AsyncSession, arq_pool: Any
) -> None:
    """approve-all with zero pending review items returns 200 with approved: 0
    and enqueues nothing."""
    await _make_review(db_session, status=ReviewStatus.approved, item_id=1)

    csrf = await _setup_and_login(client)
    resp = await client.post("/api/reviews/approve-all", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    assert resp.json()["approved"] == 0
    arq_pool.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_reviews_reject_all(
    client: AsyncClient, db_session: AsyncSession, arq_pool: Any
) -> None:
    """POST /api/reviews/reject-all rejects every pending item as a pure status
    flip — no apply job is enqueued (unlike approve-all)."""
    rv1 = await _make_review(db_session, item_id=1)
    rv2 = await _make_review(db_session, item_id=2)
    already_approved = await _make_review(db_session, status=ReviewStatus.approved, item_id=3)

    csrf = await _setup_and_login(client)
    resp = await client.post("/api/reviews/reject-all", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    assert resp.json()["rejected"] == 2

    for rv in (rv1, rv2):
        await db_session.refresh(rv)
        assert rv.status == ReviewStatus.rejected
        assert rv.resolved_at is not None

    await db_session.refresh(already_approved)
    assert already_approved.status == ReviewStatus.approved

    arq_pool.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_reviews_reject_all_idempotent(client: AsyncClient) -> None:
    """reject-all with zero pending review items returns 200 with rejected: 0."""
    csrf = await _setup_and_login(client)
    resp = await client.post("/api/reviews/reject-all", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    assert resp.json()["rejected"] == 0


@pytest.mark.asyncio
async def test_reviews_bulk_endpoints_require_auth(client: AsyncClient) -> None:
    """approve-all / reject-all reject unauthenticated callers with 401."""
    resp = await client.post("/api/reviews/approve-all", headers={"x-csrf-token": "fake"})
    assert resp.status_code == 401

    resp2 = await client.post("/api/reviews/reject-all", headers={"x-csrf-token": "fake"})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_reviews_bulk_endpoints_require_csrf(client: AsyncClient) -> None:
    """approve-all / reject-all reject cookie-authenticated calls missing the
    X-CSRF-Token header with 403."""
    await _setup_and_login(client)

    resp = await client.post("/api/reviews/approve-all")
    assert resp.status_code == 403

    resp2 = await client.post("/api/reviews/reject-all")
    assert resp2.status_code == 403


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


# ---------------------------------------------------------------------------
# Corruption vs legitimate in-place edit (docs/decisions.md)
#
# Before this fix, `_behavior_integrity` flagged ANY hash mismatch on a model
# file as `corruption` regardless of mtime, while `_behavior_re_render`
# independently reached "file updated -> re-render" for the same mismatch,
# and neither adopted the new hash as the baseline. These tests exercise the
# unified classifier in `_behavior_re_render` that replaced both.
# ---------------------------------------------------------------------------

_VALID_STL_V1 = b"""solid v1
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid v1
"""

_VALID_STL_V2 = b"""solid v2
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 2 0 0
    vertex 0 2 0
  endloop
endfacet
endsolid v2
"""


async def _make_model_item(
    db: AsyncSession,
    tmp_path: Path,
    *,
    lib_name: str,
    key: str,
    file_bytes: bytes,
    baseline_mtime: datetime,
) -> tuple[Any, Any]:
    """Create a Library + Item + one model.stl File row with a fixed baseline.

    Writes *file_bytes* to disk and stamps its mtime to *baseline_mtime* so
    the File row's stored sha256/size/mtime exactly match what's on disk —
    the starting "in sync" state each test then perturbs.
    """
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    item_dir = tmp_path / lib_name / "ab" / f"model-{key}"
    item_dir.mkdir(parents=True)
    stl_path = item_dir / "model.stl"
    stl_path.write_bytes(file_bytes)
    ts = baseline_mtime.timestamp()
    os.utime(stl_path, (ts, ts))

    lib = Library(name=lib_name, mount_path=str(tmp_path / lib_name), enabled=True)
    db.add(lib)
    await db.flush()

    item = Item(
        key=key,
        title=f"Model {key}",
        slug=f"model-{key}",
        library_id=lib.id,
        dir_path=str(item_dir),
        schema_version=1,
        updated_at=baseline_mtime,
    )
    db.add(item)
    await db.flush()

    sha = hashlib.sha256(file_bytes).hexdigest()
    f = File(
        item_id=item.id,
        path="model.stl",
        role=FileRole.model,
        size=len(file_bytes),
        sha256=sha,
        mtime=baseline_mtime,
        last_seen_size=len(file_bytes),
        last_seen_mtime=baseline_mtime,
    )
    db.add(f)
    await db.flush()

    return item, f


def _patch_no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make create_arq_pool() raise so the re_render enqueue try/except is
    exercised without needing a real Redis in the test environment — the
    ChangeLog write happens regardless (fire-and-forget, per #20)."""
    async def _raise(*_a: object, **_kw: object) -> None:
        raise RuntimeError("no redis in tests")

    monkeypatch.setattr("app.worker.arq_pool.create_arq_pool", _raise)


@pytest.mark.asyncio
async def test_reconcile_legit_edit_adopts_baseline_no_corruption(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Newer mtime + still-valid file -> baseline adopted, no corruption Issue,
    render enqueued; re-running the scan is a no-op (the core of the bug)."""
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    _patch_no_redis(monkeypatch)

    baseline_time = datetime.now(UTC) - timedelta(minutes=5)
    item, f = await _make_model_item(
        db_session, tmp_path,
        lib_name="legit_edit", key="aaa1111",
        file_bytes=_VALID_STL_V1, baseline_mtime=baseline_time,
    )

    # Simulate "opened in a slicer, saved over the same path": new content,
    # newer mtime (well beyond the 1s tolerance).
    stl_path = Path(item.dir_path) / "model.stl"
    stl_path.write_bytes(_VALID_STL_V2)
    new_mtime = datetime.now(UTC)
    os.utime(stl_path, (new_mtime.timestamp(), new_mtime.timestamp()))

    result = await reconcile_one_item(
        db_session, item,
        mode_settings={"sidecar_sync": "review", "re_render": "auto", "file_changes": "review"},
    )

    # No corruption issue.
    issues = (await db_session.execute(
        select(Issue).where(Issue.item_id == item.id, Issue.issue_type == IssueType.corruption)
    )).scalars().all()
    assert issues == []

    # Baseline adopted + render enqueued ChangeLog entries present.
    changes = (await db_session.execute(
        select(ChangeLog).where(ChangeLog.item_id == item.id)
    )).scalars().all()
    change_types = {c.change_type for c in changes}
    assert "baseline_adopted" in change_types
    assert "render_enqueued" in change_types

    # File row updated to the new hash/mtime/size.
    await db_session.refresh(f)
    assert f.sha256 == hashlib.sha256(_VALID_STL_V2).hexdigest()
    assert f.last_seen_size == len(_VALID_STL_V2)

    assert len(result.changes_applied) >= 2  # baseline_adopted + render_enqueued

    # Re-running the scan must be a no-op: no new issues/changes.
    changes_before = len(changes)
    result2 = await reconcile_one_item(
        db_session, item,
        mode_settings={"sidecar_sync": "review", "re_render": "auto", "file_changes": "review"},
    )
    changes_after = (await db_session.execute(
        select(ChangeLog).where(ChangeLog.item_id == item.id)
    )).scalars().all()
    assert len(changes_after) == changes_before
    assert result2.issues_created == []
    issues_after = (await db_session.execute(
        select(Issue).where(Issue.item_id == item.id, Issue.issue_type == IssueType.corruption)
    )).scalars().all()
    assert issues_after == []


@pytest.mark.asyncio
async def test_reconcile_newer_mtime_unparseable_file_is_corruption(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Newer mtime + a file that fails to parse -> corruption Issue with a
    detail distinguishing it from silent bit-rot."""
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    _patch_no_redis(monkeypatch)

    baseline_time = datetime.now(UTC) - timedelta(minutes=5)
    item, _f = await _make_model_item(
        db_session, tmp_path,
        lib_name="bad_write", key="bbb2222",
        file_bytes=_VALID_STL_V1, baseline_mtime=baseline_time,
    )

    # Simulate an interrupted/incomplete write: truncated content, newer mtime.
    stl_path = Path(item.dir_path) / "model.stl"
    stl_path.write_bytes(_VALID_STL_V1[:20])
    new_mtime = datetime.now(UTC)
    os.utime(stl_path, (new_mtime.timestamp(), new_mtime.timestamp()))

    result = await reconcile_one_item(
        db_session, item,
        mode_settings={"sidecar_sync": "review", "re_render": "auto", "file_changes": "review"},
    )

    assert len(result.issues_created) == 1
    issue = await db_session.get(Issue, result.issues_created[0])
    assert issue is not None
    assert issue.issue_type == IssueType.corruption
    assert issue.severity == IssueSeverity.critical
    assert "failed to parse" in issue.detail
    assert "incomplete/interrupted write" in issue.detail

    # No baseline-adopted / render-enqueued ChangeLog for this file.
    changes = (await db_session.execute(
        select(ChangeLog).where(ChangeLog.item_id == item.id)
    )).scalars().all()
    assert {c.change_type for c in changes} == set()


@pytest.mark.asyncio
async def test_reconcile_hash_change_mtime_unchanged_is_bitrot_corruption(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hash changed but mtime NOT newer than the baseline -> corruption Issue
    (silent bit-rot), with the plain "hash mismatch" detail (no parse claim)."""
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    _patch_no_redis(monkeypatch)

    baseline_time = datetime.now(UTC) - timedelta(minutes=5)
    item, _f = await _make_model_item(
        db_session, tmp_path,
        lib_name="bitrot", key="ccc3333",
        file_bytes=_VALID_STL_V1, baseline_mtime=baseline_time,
    )

    # Simulate silent on-disk corruption: content changes (different size, so
    # the cheap-first size+mtime drift check can't short-circuit the hash
    # comparison), but the mtime is forced back to the original baseline (no
    # legitimate write occurred).
    stl_path = Path(item.dir_path) / "model.stl"
    stl_path.write_bytes(_VALID_STL_V1 + b"\x00garbage-bit-rot-tail\x00")
    ts = baseline_time.timestamp()
    os.utime(stl_path, (ts, ts))

    result = await reconcile_one_item(
        db_session, item,
        mode_settings={"sidecar_sync": "review", "re_render": "auto", "file_changes": "review"},
    )

    assert len(result.issues_created) == 1
    issue = await db_session.get(Issue, result.issues_created[0])
    assert issue is not None
    assert issue.issue_type == IssueType.corruption
    assert "hash mismatch" in issue.detail
    assert "failed to parse" not in issue.detail


@pytest.mark.asyncio
async def test_reconcile_no_hash_change_is_a_noop(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hash unchanged -> nothing (no Issue, no ChangeLog, no render)."""
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    _patch_no_redis(monkeypatch)

    baseline_time = datetime.now(UTC) - timedelta(minutes=5)
    item, _f = await _make_model_item(
        db_session, tmp_path,
        lib_name="nochange", key="ddd4444",
        file_bytes=_VALID_STL_V1, baseline_mtime=baseline_time,
    )

    result = await reconcile_one_item(
        db_session, item,
        mode_settings={"sidecar_sync": "review", "re_render": "auto", "file_changes": "review"},
    )

    assert result.issues_created == []
    assert result.changes_applied == []


@pytest.mark.asyncio
async def test_reconcile_legit_3mf_edit_no_false_corruption(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The motivating case: a .3mf opened in a slicer and saved over the same
    path is a legitimate edit, not corruption."""
    from app.models.file import File, FileRole  # noqa: PLC0415
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    _patch_no_redis(monkeypatch)

    def make_3mf(vertex_x: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "3D/3dmodel.model",
                (
                    '<?xml version="1.0"?>'
                    '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
                    "<resources>"
                    '<object id="1" type="model"><mesh>'
                    "<vertices>"
                    '<vertex x="0" y="0" z="0"/>'
                    f'<vertex x="{vertex_x}" y="0" z="0"/>'
                    '<vertex x="0" y="1" z="0"/>'
                    "</vertices>"
                    '<triangles><triangle v1="0" v2="1" v3="2"/></triangles>'
                    "</mesh></object>"
                    "</resources><build/></model>"
                ).encode(),
            )
        return buf.getvalue()

    v1 = make_3mf("1")
    baseline_time = datetime.now(UTC) - timedelta(minutes=5)

    item_dir = tmp_path / "threemf_lib" / "ab" / "model-eee5555"
    item_dir.mkdir(parents=True)
    model_path = item_dir / "model.3mf"
    model_path.write_bytes(v1)
    ts = baseline_time.timestamp()
    os.utime(model_path, (ts, ts))

    lib = Library(name="threemf_lib", mount_path=str(tmp_path / "threemf_lib"), enabled=True)
    db_session.add(lib)
    await db_session.flush()

    item = Item(
        key="eee5555", title="Model eee5555", slug="model-eee5555",
        library_id=lib.id, dir_path=str(item_dir), schema_version=1,
        updated_at=baseline_time,
    )
    db_session.add(item)
    await db_session.flush()

    f = File(
        item_id=item.id, path="model.3mf", role=FileRole.model,
        size=len(v1), sha256=hashlib.sha256(v1).hexdigest(), mtime=baseline_time,
        last_seen_size=len(v1), last_seen_mtime=baseline_time,
    )
    db_session.add(f)
    await db_session.flush()

    # Re-save in the slicer: geometry changes, newer mtime.
    v2 = make_3mf("2")
    model_path.write_bytes(v2)
    new_mtime = datetime.now(UTC)
    os.utime(model_path, (new_mtime.timestamp(), new_mtime.timestamp()))

    result = await reconcile_one_item(
        db_session, item,
        mode_settings={"sidecar_sync": "review", "re_render": "auto", "file_changes": "review"},
    )

    assert result.issues_created == []
    change_types = {c.get("change_type") for c in result.changes_applied}
    assert "baseline_adopted" in change_types

    await db_session.refresh(f)
    assert f.sha256 == hashlib.sha256(v2).hexdigest()
