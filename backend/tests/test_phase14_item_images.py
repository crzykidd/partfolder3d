"""Phase 14 tests: render→Image reconcile, image upload/delete, sidecar exclusion.

Uses the same ephemeral Postgres + per-test rollback approach as other phases.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from app.models.image import Image, ImageSource

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


async def _create_library_and_item(
    client: AsyncClient,
    tmp_path: Path,
    csrf: str,
    item_title: str = "Test Item",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a library (with real dir) and an item. Returns (lib_data, item_data)."""
    mount = str(tmp_path / "library")
    Path(mount).mkdir(parents=True, exist_ok=True)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Test Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201, lib_resp.text
    lib = lib_resp.json()

    item_resp = await client.post(
        "/api/items",
        json={"title": item_title, "library_id": lib["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201, item_resp.text
    return lib, item_resp.json()


# ---------------------------------------------------------------------------
# render_item reconcile tests (direct function calls, no worker context)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_reconcile_creates_image_row(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """_reconcile_render_images creates a source=render Image row for each PNG."""
    from worker import _reconcile_render_images  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_id = item["id"]
    item_dir = Path(item["dir_path"])

    # Simulate a render PNG being written
    renders_dir = item_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    (renders_dir / "abc123.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # Run reconcile
    await _reconcile_render_images(item_id, item_dir, renders_dir, _db=db_session)

    # Verify a source=render Image row was created
    result = await db_session.execute(
        select(Image).where(
            Image.item_id == item_id,
            Image.source == ImageSource.render,
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].path == "renders/abc123.png"


@pytest.mark.asyncio
async def test_render_reconcile_sets_default_when_none(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """_reconcile_render_images sets is_default=True on the render when no default exists."""
    from worker import _reconcile_render_images  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_id = item["id"]
    item_dir = Path(item["dir_path"])

    renders_dir = item_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    (renders_dir / "def456.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    await _reconcile_render_images(item_id, item_dir, renders_dir, _db=db_session)

    result = await db_session.execute(
        select(Image).where(
            Image.item_id == item_id,
            Image.source == ImageSource.render,
            Image.is_default.is_(True),
        )
    )
    default_row = result.scalar_one_or_none()
    assert default_row is not None, "Expected render Image row to be set as default"


@pytest.mark.asyncio
async def test_render_reconcile_no_duplicate_on_rerun(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Running _reconcile_render_images twice does not create duplicate rows."""
    from worker import _reconcile_render_images  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_id = item["id"]
    item_dir = Path(item["dir_path"])

    renders_dir = item_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    (renders_dir / "aaa111.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    await _reconcile_render_images(item_id, item_dir, renders_dir, _db=db_session)
    await _reconcile_render_images(item_id, item_dir, renders_dir, _db=db_session)

    result = await db_session.execute(
        select(Image).where(
            Image.item_id == item_id,
            Image.source == ImageSource.render,
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 1, f"Expected 1 render row, got {len(rows)}"


@pytest.mark.asyncio
async def test_render_reconcile_does_not_override_curated_default(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """If a curated image is already the default, reconcile must not change it."""
    from worker import _reconcile_render_images  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_id = item["id"]
    item_dir = Path(item["dir_path"])

    # Create a curated (scraped) image row that is already default
    curated = Image(
        item_id=item_id,
        path="images/cover.jpg",
        source=ImageSource.scraped,
        is_default=True,
        order=0,
    )
    db_session.add(curated)
    await db_session.flush()

    renders_dir = item_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    (renders_dir / "bbb222.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    await _reconcile_render_images(item_id, item_dir, renders_dir, _db=db_session)

    # Reload and verify curated is still default
    await db_session.refresh(curated)
    assert curated.is_default is True

    # Render row should NOT be default
    result = await db_session.execute(
        select(Image).where(
            Image.item_id == item_id,
            Image.source == ImageSource.render,
        )
    )
    render_row = result.scalar_one_or_none()
    assert render_row is not None
    assert render_row.is_default is False


# ---------------------------------------------------------------------------
# POST /api/items/{key}/images — upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_image_creates_row_and_file(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """POST /api/items/{key}/images creates an Image row and writes the file to disk."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]
    item_dir = Path(item["dir_path"])

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x11\x00\x07\x18\xd8N\xd3\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    resp = await client.post(
        f"/api/items/{item_key}/images",
        files={"file": ("test.png", io.BytesIO(png_bytes), "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["source"] == "uploaded"
    assert data["path"].startswith("images/")

    # Verify DB row
    result = await db_session.execute(
        select(Image).where(Image.item_id == item["id"], Image.source == ImageSource.uploaded)
    )
    rows = result.scalars().all()
    assert len(rows) == 1

    # Verify file on disk
    dest = item_dir / rows[0].path
    assert dest.exists(), f"Expected uploaded file at {dest}"


@pytest.mark.asyncio
async def test_upload_image_rejects_non_image(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """POST /api/items/{key}/images rejects non-image content types."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]

    resp = await client.post(
        f"/api/items/{item_key}/images",
        files={"file": ("model.stl", io.BytesIO(b"solid ..."), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/items/{key}/images/{image_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_image_removes_row_and_file(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE /api/items/{key}/images/{id} removes the DB row and file."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]
    item_dir = Path(item["dir_path"])

    # Upload an image first
    png_bytes = b"\x89PNG\r\n\x1a\n\x00" * 4
    upload_resp = await client.post(
        f"/api/items/{item_key}/images",
        files={"file": ("upload.png", io.BytesIO(png_bytes), "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    image_data = upload_resp.json()
    image_id = image_data["id"]
    rel_path = image_data["path"]

    # Verify it exists on disk before delete
    assert (item_dir / rel_path).exists()

    # Delete
    del_resp = await client.delete(
        f"/api/items/{item_key}/images/{image_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204, del_resp.text

    # Verify row is gone
    result = await db_session.execute(
        select(Image).where(Image.id == image_id)
    )
    assert result.scalar_one_or_none() is None

    # Verify file is removed from disk
    assert not (item_dir / rel_path).exists()


@pytest.mark.asyncio
async def test_delete_default_image_reassigns(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE of the default image reassigns default to the next remaining image."""
    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_key = item["key"]

    png_bytes = b"\x89PNG\r\n\x1a\n\x00" * 4

    # Upload two images
    resp1 = await client.post(
        f"/api/items/{item_key}/images",
        files={"file": ("first.png", io.BytesIO(png_bytes), "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp1.status_code == 201
    img1_id = resp1.json()["id"]

    resp2 = await client.post(
        f"/api/items/{item_key}/images",
        files={"file": ("second.png", io.BytesIO(png_bytes), "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp2.status_code == 201
    img2_id = resp2.json()["id"]

    # Set img1 as default
    await client.patch(
        f"/api/items/{item_key}/default-image",
        json={"image_id": img1_id},
        headers={"X-CSRF-Token": csrf},
    )

    # Delete the default (img1)
    del_resp = await client.delete(
        f"/api/items/{item_key}/images/{img1_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204

    # img2 should now be default
    result = await db_session.execute(
        select(Image).where(Image.id == img2_id)
    )
    img2 = result.scalar_one_or_none()
    assert img2 is not None
    assert img2.is_default is True


# ---------------------------------------------------------------------------
# Sidecar exclusion of renders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_images_excluded_from_sidecar(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Render Image rows are NOT written to the sidecar YAML."""
    from worker import _reconcile_render_images  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)
    item_id = item["id"]
    item_key = item["key"]
    item_dir = Path(item["dir_path"])

    # Create a render PNG and reconcile
    renders_dir = item_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    (renders_dir / "ccc333.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    await _reconcile_render_images(item_id, item_dir, renders_dir, _db=db_session)

    # Trigger a sidecar write via a no-op update (title stays same)
    resp = await client.patch(
        f"/api/items/{item_key}",
        json={"description": "updated description"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text

    # Read sidecar YAML directly from disk
    sidecar_files = list(item_dir.glob("*.yml"))
    assert sidecar_files, "No sidecar file found on disk"
    sc = yaml.safe_load(sidecar_files[0].read_text(encoding="utf-8"))
    images_in_sidecar = sc.get("images", [])

    # No render images should appear in the sidecar
    render_entries = [img for img in images_in_sidecar if img.get("source") == "render"]
    assert not render_entries, f"Render images found in sidecar: {render_entries}"
