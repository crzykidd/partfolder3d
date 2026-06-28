"""Phase 9 tests: backup, export, tag admin, site capabilities, API keys.

Uses the same ephemeral Postgres + per-test rollback approach as prior phases.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backup import BackupRecord
from app.models.site_capability import SiteCapability, SiteToken
from app.models.tag import Tag, TagAlias, TagStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient, tmp_path: Path) -> str:
    """Initialize instance and log in as admin; returns CSRF token."""
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
# Backup record model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backup_record_create(db_session: AsyncSession) -> None:
    """BackupRecord can be created and retrieved."""
    rec = BackupRecord(
        filename="backup_2026-06-27T04-00-00.tar.gz",
        path="/data/backups/backup_2026-06-27T04-00-00.tar.gz",
        status="pending",
    )
    db_session.add(rec)
    await db_session.flush()

    result = await db_session.execute(
        select(BackupRecord).where(BackupRecord.filename.like("backup_%"))
    )
    found = result.scalar_one_or_none()
    assert found is not None
    assert found.status == "pending"
    assert found.size_bytes is None


# ---------------------------------------------------------------------------
# Backup API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backup_list_empty(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/admin/backups returns empty list when no backups."""
    await _setup_and_login(client, tmp_path)
    resp = await client.get("/api/admin/backups")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_backup_list_with_record(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/admin/backups returns existing records."""
    await _setup_and_login(client, tmp_path)
    rec = BackupRecord(
        filename="backup_test.tar.gz",
        path="/data/backups/backup_test.tar.gz",
        status="ready",
        size_bytes=12345,
    )
    db_session.add(rec)
    await db_session.flush()

    resp = await client.get("/api/admin/backups")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["filename"] == "backup_test.tar.gz"
    assert data[0]["size_bytes"] == 12345
    assert data[0]["status"] == "ready"


@pytest.mark.asyncio
async def test_backup_settings_default(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/admin/backups/settings returns default retention count."""
    await _setup_and_login(client, tmp_path)
    resp = await client.get("/api/admin/backups/settings")
    assert resp.status_code == 200
    assert resp.json()["retention_count"] == 10


@pytest.mark.asyncio
async def test_backup_settings_update(client: AsyncClient, tmp_path: Path) -> None:
    """PUT /api/admin/backups/settings updates retention count."""
    csrf = await _setup_and_login(client, tmp_path)
    resp = await client.put(
        "/api/admin/backups/settings",
        json={"retention_count": 5},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["retention_count"] == 5

    # Verify persisted
    resp2 = await client.get("/api/admin/backups/settings")
    assert resp2.json()["retention_count"] == 5


@pytest.mark.asyncio
async def test_backup_download_not_found(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/admin/backups/9999/download → 404."""
    await _setup_and_login(client, tmp_path)
    resp = await client.get("/api/admin/backups/9999/download")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_backup_delete(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """DELETE /api/admin/backups/{id} removes the record."""
    csrf = await _setup_and_login(client, tmp_path)
    rec = BackupRecord(
        filename="backup_to_delete.tar.gz",
        path="/data/backups/backup_to_delete.tar.gz",
        status="ready",
    )
    db_session.add(rec)
    await db_session.flush()
    rec_id = rec.id

    resp = await client.delete(
        f"/api/admin/backups/{rec_id}",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 204

    result = await db_session.execute(
        select(BackupRecord).where(BackupRecord.id == rec_id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# In-process backup (run_db_backup)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_db_backup_creates_archive(tmp_path: Path) -> None:
    """run_db_backup produces a .tar.gz archive with expected contents."""
    import tarfile

    from app.crypto import ensure_key
    from app.worker.backup import run_db_backup

    # Ensure key exists in tmp_path (isolated_data_dir fixture already set DATA_DIR)
    ensure_key()

    archive_path = await run_db_backup(str(tmp_path))
    assert archive_path.exists(), "Archive file must be created"
    assert archive_path.suffix == ".gz"
    assert archive_path.stat().st_size > 0, "Archive must not be empty"

    # Verify archive contents
    with tarfile.open(archive_path, "r:gz") as tf:
        members = tf.getnames()
    assert "metadata.json" in members, "metadata.json must be in archive"
    assert "db.json.gz" in members, "db.json.gz must be in archive"
    # secret.key may be missing if DATA_DIR/config/secret.key does not exist yet


@pytest.mark.asyncio
async def test_run_db_backup_includes_secret_key(tmp_path: Path) -> None:
    """run_db_backup includes config/secret.key when it exists."""
    import tarfile

    from app.crypto import ensure_key
    from app.worker.backup import run_db_backup

    ensure_key()

    archive_path = await run_db_backup(str(tmp_path))
    with tarfile.open(archive_path, "r:gz") as tf:
        members = tf.getnames()
    assert "config/secret.key" in members, "secret.key must be included in archive"


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_catalog_empty(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/admin/export/catalog returns valid JSON with empty collections."""
    await _setup_and_login(client, tmp_path)
    resp = await client.get("/api/admin/export/catalog")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    data = resp.json()
    assert "exported_at" in data
    assert "items" in data
    assert "tags" in data
    assert "creators" in data
    assert "tag_aliases" in data


# ---------------------------------------------------------------------------
# Tag admin — pending list + approve + reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_admin_pending_list(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """GET /api/admin/tags/pending returns pending tags."""
    await _setup_and_login(client, tmp_path)
    pending = Tag(name="test-pending-tag", status=TagStatus.pending)
    active = Tag(name="test-active-tag", status=TagStatus.active)
    db_session.add(pending)
    db_session.add(active)
    await db_session.flush()

    resp = await client.get("/api/admin/tags/pending")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "test-pending-tag" in names
    assert "test-active-tag" not in names


@pytest.mark.asyncio
async def test_tag_admin_approve(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """POST /api/admin/tags/{id}/approve promotes pending → active."""
    csrf = await _setup_and_login(client, tmp_path)
    tag = Tag(name="to-approve", status=TagStatus.pending)
    db_session.add(tag)
    await db_session.flush()

    resp = await client.post(
        f"/api/admin/tags/{tag.id}/approve",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_tag_admin_reject(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """POST /api/admin/tags/{id}/reject deletes a pending tag."""
    csrf = await _setup_and_login(client, tmp_path)
    tag = Tag(name="to-reject", status=TagStatus.pending)
    db_session.add(tag)
    await db_session.flush()
    tag_id = tag.id

    resp = await client.post(
        f"/api/admin/tags/{tag_id}/reject",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 204

    result = await db_session.execute(select(Tag).where(Tag.id == tag_id))
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Tag admin — category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_set_category(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """PATCH /api/admin/tags/{id}/category sets the category."""
    csrf = await _setup_and_login(client, tmp_path)
    tag = Tag(name="material-pla", status=TagStatus.active)
    db_session.add(tag)
    await db_session.flush()

    resp = await client.patch(
        f"/api/admin/tags/{tag.id}/category",
        json={"category": "material"},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["category"] == "material"


@pytest.mark.asyncio
async def test_tag_clear_category(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """PATCH /api/admin/tags/{id}/category with null clears it."""
    csrf = await _setup_and_login(client, tmp_path)
    tag = Tag(name="categorized-tag", status=TagStatus.active, category="old-cat")
    db_session.add(tag)
    await db_session.flush()

    resp = await client.patch(
        f"/api/admin/tags/{tag.id}/category",
        json={"category": None},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["category"] is None


# ---------------------------------------------------------------------------
# Tag admin — aliases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_alias_add_and_list(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """Add and list aliases for a tag."""
    csrf = await _setup_and_login(client, tmp_path)
    tag = Tag(name="canonical-tag", status=TagStatus.active)
    db_session.add(tag)
    await db_session.flush()

    resp = await client.post(
        f"/api/admin/tags/{tag.id}/aliases",
        json={"alias": "old-name"},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 201
    assert resp.json()["alias"] == "old-name"

    list_resp = await client.get(f"/api/admin/tags/{tag.id}/aliases")
    assert list_resp.status_code == 200
    assert any(a["alias"] == "old-name" for a in list_resp.json())


@pytest.mark.asyncio
async def test_tag_alias_delete(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """DELETE /api/admin/tags/aliases/{id} removes the alias."""
    csrf = await _setup_and_login(client, tmp_path)
    tag = Tag(name="tag-with-alias", status=TagStatus.active)
    db_session.add(tag)
    await db_session.flush()
    alias = TagAlias(alias="alias-to-delete", tag_id=tag.id)
    db_session.add(alias)
    await db_session.flush()
    alias_id = alias.id

    resp = await client.delete(
        f"/api/admin/tags/aliases/{alias_id}",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 204

    result = await db_session.execute(
        select(TagAlias).where(TagAlias.id == alias_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_tag_alias_duplicate_rejected(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """Adding a duplicate alias returns 409."""
    csrf = await _setup_and_login(client, tmp_path)
    tag = Tag(name="tag-unique-alias", status=TagStatus.active)
    db_session.add(tag)
    await db_session.flush()
    db_session.add(TagAlias(alias="dup-alias", tag_id=tag.id))
    await db_session.flush()

    resp = await client.post(
        f"/api/admin/tags/{tag.id}/aliases",
        json={"alias": "dup-alias"},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Tag merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_merge(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """POST /api/admin/tags/{src}/merge-into/{tgt} merges tags."""
    csrf = await _setup_and_login(client, tmp_path)
    src = Tag(name="src-tag", status=TagStatus.active, popularity_count=3)
    tgt = Tag(name="tgt-tag", status=TagStatus.active, popularity_count=7)
    db_session.add(src)
    db_session.add(tgt)
    await db_session.flush()

    resp = await client.post(
        f"/api/admin/tags/{src.id}/merge-into/{tgt.id}",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["merged"] is True
    assert data["target_id"] == tgt.id
    assert data["source_name"] == "src-tag"

    # src tag deleted
    src_result = await db_session.execute(select(Tag).where(Tag.id == src.id))
    assert src_result.scalar_one_or_none() is None

    # alias created for src.name → tgt
    alias_result = await db_session.execute(
        select(TagAlias).where(TagAlias.alias == "src-tag", TagAlias.tag_id == tgt.id)
    )
    assert alias_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_tag_merge_self_rejected(client: AsyncClient, tmp_path: Path) -> None:
    """Merging a tag into itself returns 422."""
    csrf = await _setup_and_login(client, tmp_path)
    resp = await client.post(
        "/api/admin/tags/1/merge-into/1",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Site capabilities admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_site_capabilities_list_empty(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/admin/site-capabilities returns empty list initially."""
    await _setup_and_login(client, tmp_path)
    resp = await client.get("/api/admin/site-capabilities")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_site_capabilities_crud(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """Site capability PATCH + list works."""
    csrf = await _setup_and_login(client, tmp_path)
    cap = SiteCapability(
        domain="thingiverse.com",
        can_scrape_metadata=True,
        can_scrape_images=True,
        requires_token=False,
        is_manual_only=False,
    )
    db_session.add(cap)
    await db_session.flush()

    # List
    resp = await client.get("/api/admin/site-capabilities")
    assert resp.status_code == 200
    assert any(c["domain"] == "thingiverse.com" for c in resp.json())

    # Patch
    resp2 = await client.patch(
        "/api/admin/site-capabilities/thingiverse.com",
        json={"is_manual_only": True, "notes": "Rate-limited"},
        headers={"x-csrf-token": csrf},
    )
    assert resp2.status_code == 200
    assert resp2.json()["is_manual_only"] is True
    assert resp2.json()["notes"] == "Rate-limited"

    # Get
    resp3 = await client.get("/api/admin/site-capabilities/thingiverse.com")
    assert resp3.status_code == 200
    assert resp3.json()["is_manual_only"] is True


@pytest.mark.asyncio
async def test_site_capabilities_set_token(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """POST /api/admin/site-capabilities/{domain}/token stores encrypted token."""
    csrf = await _setup_and_login(client, tmp_path)
    cap = SiteCapability(
        domain="myminifactory.com",
        can_scrape_metadata=True,
        can_scrape_images=True,
        requires_token=False,
        is_manual_only=False,
    )
    db_session.add(cap)
    await db_session.flush()

    resp = await client.post(
        "/api/admin/site-capabilities/myminifactory.com/token",
        json={"token": "my-secret-api-token"},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_token"] is True
    assert data["requires_token"] is True

    # Verify token is stored encrypted (not plaintext)
    tok_result = await db_session.execute(
        select(SiteToken).where(SiteToken.domain == "myminifactory.com")
    )
    tok = tok_result.scalar_one_or_none()
    assert tok is not None
    assert tok.encrypted_token != "my-secret-api-token"  # must be encrypted

    from app.crypto import decrypt
    assert decrypt(tok.encrypted_token) == "my-secret-api-token"


@pytest.mark.asyncio
async def test_site_capabilities_reprobe(
    client: AsyncClient, tmp_path: Path, db_session: AsyncSession
) -> None:
    """POST /api/admin/site-capabilities/{domain}/reprobe clears last_probed_at."""
    from datetime import UTC, datetime

    csrf = await _setup_and_login(client, tmp_path)
    cap = SiteCapability(
        domain="prusaprinters.org",
        can_scrape_metadata=True,
        can_scrape_images=True,
        requires_token=False,
        is_manual_only=False,
        last_probed_at=datetime.now(UTC),
    )
    db_session.add(cap)
    await db_session.flush()

    resp = await client.post(
        "/api/admin/site-capabilities/prusaprinters.org/reprobe",
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["last_probed_at"] is None


# ---------------------------------------------------------------------------
# API key auth works across admin endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_key_bearer_auth_on_admin_endpoint(
    client: AsyncClient, tmp_path: Path
) -> None:
    """Bearer API key auth works for admin endpoints (Phase 9 API parity)."""
    csrf = await _setup_and_login(client, tmp_path)

    # Create an API key
    resp = await client.post(
        "/api/api-keys",
        json={"label": "test-key"},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 201
    raw_key = resp.json()["key"]

    # Log out (clear cookie)
    await client.post("/api/auth/logout", headers={"x-csrf-token": csrf})

    # Use Bearer token to access admin backup list
    resp2 = await client.get(
        "/api/admin/backups",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert resp2.status_code == 200  # admin user + valid Bearer key → success
