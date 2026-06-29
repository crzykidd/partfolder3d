"""Phase 15 tests: local-modification tracking (source_baseline, locally_modified, override).

Tests:
  - Import commit captures source_baseline from model files when source_url is set.
  - Import commit leaves source_baseline null when no source_url.
  - scan engine (reconcile_one_item) flips locally_modified when model file hashes change.
  - scan engine clears locally_modified when files match baseline again.
  - manual override wins over auto detection.
  - public share response carries is_modified.

Uses the same ephemeral Postgres + per-test rollback approach as other phases.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File, FileRole
from app.models.item import Item
from app.models.library import Library

# ---------------------------------------------------------------------------
# Auth helper (same as other test files)
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient, tmp_path: Path) -> str:
    """Initialize instance and log in as admin; returns CSRF token."""
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


def _make_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# Helpers to build minimal item + file rows
# ---------------------------------------------------------------------------


async def _make_library(db: AsyncSession, tmp_path: Path) -> Library:
    lib = Library(
        name="Test Library",
        mount_path=str(tmp_path / "lib"),
        enabled=True,
    )
    db.add(lib)
    await db.flush()
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    return lib


async def _make_item_with_files(
    db: AsyncSession,
    tmp_path: Path,
    library: Library,
    source_url: str | None = "https://example.com/design/42",
    model_hashes: dict[str, str] | None = None,
) -> Item:
    """Create a minimal item + file rows; optionally set source_baseline."""
    item_dir = tmp_path / "lib" / "ab" / "my-item-abc123"
    item_dir.mkdir(parents=True, exist_ok=True)

    item = Item(
        key="abc123",
        title="My Item",
        slug="my-item-abc123",
        source_url=source_url,
        source_site="example.com" if source_url else None,
        library_id=library.id,
        dir_path=str(item_dir),
        schema_version=1,
        locally_modified=False,
        source_baseline=model_hashes or ({"model.stl": "aaa"} if source_url else None),
    )
    db.add(item)
    await db.flush()

    # Add a model file row
    if model_hashes:
        for path, sha in model_hashes.items():
            f = File(
                item_id=item.id,
                path=path,
                role=FileRole.model,
                size=100,
                sha256=sha,
                mtime=datetime.now(UTC),
                last_seen_size=100,
                last_seen_mtime=datetime.now(UTC),
            )
            db.add(f)
    else:
        f = File(
            item_id=item.id,
            path="model.stl",
            role=FileRole.model,
            size=100,
            sha256="aaa",
            mtime=datetime.now(UTC),
            last_seen_size=100,
            last_seen_mtime=datetime.now(UTC),
        )
        db.add(f)
    await db.flush()
    return item


# ---------------------------------------------------------------------------
# Test: _effective_is_modified logic
# ---------------------------------------------------------------------------


def test_effective_is_modified_auto_false() -> None:
    """Auto mode: not locally_modified → is_modified False."""
    from app.routers.items import _effective_is_modified  # noqa: PLC0415

    class FakeItem:
        locally_modified = False
        modified_override = None

    assert _effective_is_modified(FakeItem()) is False  # type: ignore[arg-type]


def test_effective_is_modified_auto_true() -> None:
    """Auto mode: locally_modified=True → is_modified True."""
    from app.routers.items import _effective_is_modified  # noqa: PLC0415

    class FakeItem:
        locally_modified = True
        modified_override = None

    assert _effective_is_modified(FakeItem()) is True  # type: ignore[arg-type]


def test_effective_is_modified_override_modified() -> None:
    """Override='modified' wins even if locally_modified=False."""
    from app.routers.items import _effective_is_modified  # noqa: PLC0415

    class FakeItem:
        locally_modified = False
        modified_override = "modified"

    assert _effective_is_modified(FakeItem()) is True  # type: ignore[arg-type]


def test_effective_is_modified_override_original() -> None:
    """Override='original' wins even if locally_modified=True."""
    from app.routers.items import _effective_is_modified  # noqa: PLC0415

    class FakeItem:
        locally_modified = True
        modified_override = "original"

    assert _effective_is_modified(FakeItem()) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test: scan engine updates locally_modified
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_detects_modification(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Changing a model file's hash flips locally_modified on next reconcile."""
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    library = await _make_library(db_session, tmp_path)

    # Baseline: model.stl has hash "aaa"
    item = await _make_item_with_files(
        db_session, tmp_path, library,
        source_url="https://example.com/design/42",
        model_hashes={"model.stl": "aaa"},
    )
    item.source_baseline = {"model.stl": "aaa"}
    await db_session.flush()

    # Now "change" the model file hash in the DB (simulate file changed on disk)
    file_result = await db_session.execute(
        select(File).where(File.item_id == item.id, File.role == FileRole.model)
    )
    f = file_result.scalar_one()
    f.sha256 = "bbb"  # different from baseline
    await db_session.flush()

    # Run reconcile (skip behaviors that need a real filesystem)
    with patch("app.worker.reconcile._behavior_sidecar_sync"), \
         patch("app.worker.reconcile._behavior_file_changes"), \
         patch("app.worker.reconcile._behavior_re_render"), \
         patch("app.worker.reconcile._behavior_integrity"):
        result = await reconcile_one_item(db_session, item, source="test")

    # Reload item
    await db_session.refresh(item)
    assert item.locally_modified is True
    assert item.locally_modified_at is not None
    # Result should record the change
    assert any(
        c.get("behavior") == "modified_tracking"
        for c in result.changes_applied
    )


@pytest.mark.asyncio
async def test_reconcile_clears_modification_when_files_match(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """When model files match baseline again, locally_modified is cleared."""
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    library = await _make_library(db_session, tmp_path)
    item = await _make_item_with_files(
        db_session, tmp_path, library,
        source_url="https://example.com/design/42",
        model_hashes={"model.stl": "aaa"},
    )
    # Pre-set as modified
    item.source_baseline = {"model.stl": "aaa"}
    item.locally_modified = True
    item.locally_modified_at = datetime.now(UTC)
    await db_session.flush()

    # File in DB matches baseline (hash "aaa")
    file_result = await db_session.execute(
        select(File).where(File.item_id == item.id, File.role == FileRole.model)
    )
    f = file_result.scalar_one()
    f.sha256 = "aaa"  # matches baseline
    await db_session.flush()

    with patch("app.worker.reconcile._behavior_sidecar_sync"), \
         patch("app.worker.reconcile._behavior_file_changes"), \
         patch("app.worker.reconcile._behavior_re_render"), \
         patch("app.worker.reconcile._behavior_integrity"):
        result = await reconcile_one_item(db_session, item, source="test")

    await db_session.refresh(item)
    assert item.locally_modified is False
    assert any(
        c.get("behavior") == "modified_tracking"
        for c in result.changes_applied
    )


@pytest.mark.asyncio
async def test_reconcile_skips_null_baseline(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Items with null source_baseline are skipped (no source_url at import)."""
    from app.worker.reconcile import reconcile_one_item  # noqa: PLC0415

    library = await _make_library(db_session, tmp_path)
    item = await _make_item_with_files(
        db_session, tmp_path, library,
        source_url=None,
        model_hashes={"model.stl": "aaa"},
    )
    item.source_baseline = None
    await db_session.flush()

    # Change the file hash — should NOT flip locally_modified
    file_result = await db_session.execute(
        select(File).where(File.item_id == item.id)
    )
    f = file_result.scalar_one()
    f.sha256 = "totally_different"
    await db_session.flush()

    with patch("app.worker.reconcile._behavior_sidecar_sync"), \
         patch("app.worker.reconcile._behavior_file_changes"), \
         patch("app.worker.reconcile._behavior_re_render"), \
         patch("app.worker.reconcile._behavior_integrity"):
        result = await reconcile_one_item(db_session, item, source="test")

    await db_session.refresh(item)
    assert item.locally_modified is False
    assert not any(
        c.get("behavior") == "modified_tracking"
        for c in result.changes_applied
    )


# ---------------------------------------------------------------------------
# Test: manual override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_override_modified(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """override='modified' returns is_modified=True even when auto would be False."""
    from app.routers.items import _effective_is_modified  # noqa: PLC0415

    library = await _make_library(db_session, tmp_path)
    item = await _make_item_with_files(
        db_session, tmp_path, library,
        source_url="https://example.com/design/1",
        model_hashes={"model.stl": "aaa"},
    )
    item.source_baseline = {"model.stl": "aaa"}
    item.locally_modified = False
    item.modified_override = "modified"
    await db_session.flush()

    assert _effective_is_modified(item) is True


@pytest.mark.asyncio
async def test_manual_override_via_api(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """PATCH /api/items/{key}/modified-override sets the override and returns is_modified."""
    csrf = await _setup_and_login(client, tmp_path)

    # Create a library via API
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "API Lib", "mount_path": str(tmp_path / "apilib")},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    lib_id = lib_resp.json()["id"]
    (tmp_path / "apilib").mkdir(parents=True, exist_ok=True)

    # Create an item via API
    item_resp = await client.post(
        "/api/items",
        json={
            "title": "Test Item",
            "library_id": lib_id,
            "source_url": "https://example.com/design/99",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201
    item_key = item_resp.json()["key"]

    # Set override to 'modified'
    patch_resp = await client.patch(
        f"/api/items/{item_key}/modified-override",
        json={"override": "modified"},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["is_modified"] is True
    assert data["modified_override"] == "modified"

    # Clear override
    clear_resp = await client.patch(
        f"/api/items/{item_key}/modified-override",
        json={"override": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert clear_resp.status_code == 200
    data2 = clear_resp.json()
    assert data2["modified_override"] is None
    # is_modified reverts to locally_modified (false by default)
    assert data2["is_modified"] is False


# ---------------------------------------------------------------------------
# Test: public share carries is_modified
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_share_carries_is_modified(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Public share response includes is_modified based on the item's effective state."""
    csrf = await _setup_and_login(client, tmp_path)

    # Library
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Share Lib", "mount_path": str(tmp_path / "sharelib")},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    lib_id = lib_resp.json()["id"]
    (tmp_path / "sharelib").mkdir(parents=True, exist_ok=True)

    # Item with source_url
    item_resp = await client.post(
        "/api/items",
        json={
            "title": "Share Item",
            "library_id": lib_id,
            "source_url": "https://example.com/design/100",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201
    item_key = item_resp.json()["key"]

    # Mint share link
    share_resp = await client.post(
        f"/api/items/{item_key}/shares",
        json={"expires_days": 7},
        headers={"X-CSRF-Token": csrf},
    )
    assert share_resp.status_code == 201
    token = share_resp.json()["token"]

    # Public share — is_modified should be False by default
    pub_resp = await client.get(f"/api/public/share/{token}")
    assert pub_resp.status_code == 200
    pub_data = pub_resp.json()
    assert "is_modified" in pub_data
    assert pub_data["is_modified"] is False

    # Set override to modified on item
    await client.patch(
        f"/api/items/{item_key}/modified-override",
        json={"override": "modified"},
        headers={"X-CSRF-Token": csrf},
    )

    # Public share now shows is_modified=True
    pub_resp2 = await client.get(f"/api/public/share/{token}")
    assert pub_resp2.status_code == 200
    assert pub_resp2.json()["is_modified"] is True


# ---------------------------------------------------------------------------
# Test: sidecar includes modified_state
# ---------------------------------------------------------------------------


def test_sidecar_includes_modified_state(tmp_path: Path) -> None:
    """build_sidecar writes modified_state block when source_url is set."""
    from app.storage.sidecar import SidecarModifiedState, build_sidecar  # noqa: PLC0415

    class FakeItem:
        key = "abc123"
        title = "My Item"
        slug = "my-item-abc123"
        schema_version = 1
        description = None
        source_url = "https://example.com/design/1"
        source_site = "example.com"
        license = None
        creator = None
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)
        locally_modified = True
        locally_modified_at = datetime.now(UTC)
        modified_override = None

    data = build_sidecar(FakeItem())  # type: ignore[arg-type]
    assert data.modified_state is not None
    assert isinstance(data.modified_state, SidecarModifiedState)
    assert data.modified_state.locally_modified is True
    assert data.modified_state.source == "https://example.com/design/1"


def test_sidecar_no_modified_state_without_source_url(tmp_path: Path) -> None:
    """build_sidecar omits modified_state when source_url is None."""
    from app.storage.sidecar import build_sidecar  # noqa: PLC0415

    class FakeItem:
        key = "def456"
        title = "No Source Item"
        slug = "no-source-item-def456"
        schema_version = 1
        description = None
        source_url = None
        source_site = None
        license = None
        creator = None
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)
        locally_modified = False
        locally_modified_at = None
        modified_override = None

    data = build_sidecar(FakeItem())  # type: ignore[arg-type]
    assert data.modified_state is None


# ---------------------------------------------------------------------------
# Test: import commit captures source_baseline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_item_detail_includes_modified_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """GET /api/items/{key} includes is_modified, locally_modified_at, modified_override."""
    csrf = await _setup_and_login(client, tmp_path)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Fields Lib", "mount_path": str(tmp_path / "fieldslib")},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    lib_id = lib_resp.json()["id"]
    (tmp_path / "fieldslib").mkdir(parents=True, exist_ok=True)

    item_resp = await client.post(
        "/api/items",
        json={"title": "Fields Item", "library_id": lib_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201
    item_key = item_resp.json()["key"]

    get_resp = await client.get(f"/api/items/{item_key}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "is_modified" in data
    assert "locally_modified_at" in data
    assert "modified_override" in data
    assert data["is_modified"] is False
    assert data["locally_modified_at"] is None
    assert data["modified_override"] is None
