"""Tests: import-management bundle (delete session, delete session image, inbox dir).

Covers:
  A. DELETE /api/import-sessions/{id}
     - removes session row + cascade images/files
     - committed Items are NOT touched
     - 404 on missing session

  B. DELETE /api/import-sessions/{id}/images/{image_id}
     - removes image row
     - reassigns default to next image when default was deleted
     - clears default_image_path when last image removed
     - 404 on foreign/missing image_id

  C. PATCH default_image_path / commit default image (issue #14)
     - PATCH syncs is_default flags on ImportSessionImage rows
     - full commit flow: PATCH-selected default survives into the committed Item
     - commit-side fallback: default_image_path honored when is_default not set
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_session import (
    ImportSession,
    ImportSessionImage,
)

# ---------------------------------------------------------------------------
# Auth + session helpers
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient) -> tuple[str, int]:
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


async def _create_session_via_api(client: AsyncClient, csrf: str) -> dict:
    """Create a draft upload session via POST /api/import-sessions."""
    resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    return resp.json()


async def _add_image(
    db: AsyncSession,
    session_id: uuid.UUID,
    path: str,
    order: int = 0,
    is_default: bool = False,
    is_url: bool = True,
) -> ImportSessionImage:
    img = ImportSessionImage(
        session_id=session_id,
        path=path,
        is_url=is_url,
        source="scrape",
        order=order,
        is_default=is_default,
    )
    db.add(img)
    await db.flush()
    await db.refresh(img)
    return img


# ---------------------------------------------------------------------------
# A. Delete session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_session_removes_row_and_cascade(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE /api/import-sessions/{id} removes the row and cascades images."""
    csrf, _uid = await _setup_and_login(client)
    sess = await _create_session_via_api(client, csrf)
    sid = uuid.UUID(sess["id"])

    # Add two images directly
    await _add_image(db_session, sid, "http://example.com/a.jpg", order=0, is_default=True)
    await _add_image(db_session, sid, "http://example.com/b.jpg", order=1)

    resp = await client.delete(
        f"/api/import-sessions/{sid}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204

    # Session row gone
    assert (
        await db_session.execute(select(ImportSession).where(ImportSession.id == sid))
    ).scalar_one_or_none() is None

    # Images cascade-deleted
    imgs = (
        await db_session.execute(
            select(ImportSessionImage).where(ImportSessionImage.session_id == sid)
        )
    ).scalars().all()
    assert len(imgs) == 0


@pytest.mark.asyncio
async def test_delete_session_cleans_staging_dir(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Staging dir under DATA_DIR is removed when the session is deleted."""
    csrf, _uid = await _setup_and_login(client)
    sess = await _create_session_via_api(client, csrf)
    sid = uuid.UUID(sess["id"])

    # The session has a staging_dir created by the API; verify it exists
    staging_dir = Path(sess["staging_dir"]) if sess.get("staging_dir") else None
    # If no staging_dir (URL session), set one manually via DB
    if staging_dir is None:
        staging_dir = tmp_path / "staging" / "manual"
        staging_dir.mkdir(parents=True)
        db_row = (
            await db_session.execute(select(ImportSession).where(ImportSession.id == sid))
        ).scalar_one()
        db_row.staging_dir = str(staging_dir)
        await db_session.flush()
    else:
        staging_dir.mkdir(parents=True, exist_ok=True)

    sentinel = staging_dir / "model.stl"
    sentinel.write_bytes(b"STL")
    assert sentinel.exists()

    resp = await client.delete(
        f"/api/import-sessions/{sid}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204
    assert not staging_dir.exists()


@pytest.mark.asyncio
async def test_delete_session_does_not_touch_committed_item(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Deleting a session leaves any committed Item row untouched."""
    from app.models.item import Item  # noqa: PLC0415
    from app.models.library import Library  # noqa: PLC0415

    csrf, _uid = await _setup_and_login(client)

    lib = Library(name="lib", mount_path=str(tmp_path / "lib"), enabled=True)
    db_session.add(lib)
    await db_session.flush()

    item = Item(
        key="ABCD1234",
        title="Committed Thing",
        slug="committed-thing-ABCD1234",
        library_id=lib.id,
        dir_path=str(tmp_path / "item"),
        schema_version=1,
    )
    db_session.add(item)
    await db_session.flush()

    # Create session via API, then mark it committed with item_id
    sess = await _create_session_via_api(client, csrf)
    sid = uuid.UUID(sess["id"])
    db_row = (
        await db_session.execute(select(ImportSession).where(ImportSession.id == sid))
    ).scalar_one()
    from app.models.import_session import ImportSessionStatus  # noqa: PLC0415
    db_row.status = ImportSessionStatus.committed
    db_row.item_id = item.id
    await db_session.flush()

    resp = await client.delete(
        f"/api/import-sessions/{sid}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204

    # Session gone
    assert (
        await db_session.execute(select(ImportSession).where(ImportSession.id == sid))
    ).scalar_one_or_none() is None

    # Item untouched
    surviving = (
        await db_session.execute(select(Item).where(Item.id == item.id))
    ).scalar_one_or_none()
    assert surviving is not None
    assert surviving.title == "Committed Thing"


@pytest.mark.asyncio
async def test_delete_session_404_on_missing(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    await _setup_and_login(client)
    resp = await client.delete(
        f"/api/import-sessions/{uuid.uuid4()}",
        headers={"X-CSRF-Token": (client.cookies.get("pf3d_csrf", ""))},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# C. Delete session image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_session_image_removes_row(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """DELETE /api/import-sessions/{id}/images/{img_id} removes the image row."""
    csrf, _uid = await _setup_and_login(client)
    sess = await _create_session_via_api(client, csrf)
    sid = uuid.UUID(sess["id"])

    img = await _add_image(db_session, sid, "http://example.com/x.jpg", order=0)

    resp = await client.delete(
        f"/api/import-sessions/{sid}/images/{img.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    gone = (
        await db_session.execute(
            select(ImportSessionImage).where(ImportSessionImage.id == img.id)
        )
    ).scalar_one_or_none()
    assert gone is None


@pytest.mark.asyncio
async def test_delete_default_image_reassigns_default(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Deleting the default image assigns is_default to the next image."""
    csrf, _uid = await _setup_and_login(client)
    sess = await _create_session_via_api(client, csrf)
    sid = uuid.UUID(sess["id"])

    img_default = await _add_image(
        db_session, sid, "http://example.com/d.jpg", order=0, is_default=True
    )
    img_other = await _add_image(
        db_session, sid, "http://example.com/e.jpg", order=1, is_default=False
    )

    resp = await client.delete(
        f"/api/import-sessions/{sid}/images/{img_default.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()

    returned_ids = [i["id"] for i in data["images"]]
    assert img_default.id not in returned_ids
    assert img_other.id in returned_ids

    remaining = next(i for i in data["images"] if i["id"] == img_other.id)
    assert remaining["is_default"] is True
    assert data["default_image_path"] == img_other.path

    await db_session.refresh(img_other)
    assert img_other.is_default is True


@pytest.mark.asyncio
async def test_delete_last_image_clears_default_path(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Deleting the only image clears session.default_image_path."""
    csrf, _uid = await _setup_and_login(client)
    sess = await _create_session_via_api(client, csrf)
    sid = uuid.UUID(sess["id"])

    img = await _add_image(
        db_session, sid, "http://example.com/only.jpg", order=0, is_default=True
    )

    resp = await client.delete(
        f"/api/import-sessions/{sid}/images/{img.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["images"] == []
    assert data["default_image_path"] is None


@pytest.mark.asyncio
async def test_delete_session_image_removes_staged_file(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Deleting a local image removes the staged file from disk."""
    csrf, _uid = await _setup_and_login(client)
    sess = await _create_session_via_api(client, csrf)
    sid = uuid.UUID(sess["id"])

    # Use the session's staging_dir (created by the upload-session API)
    staging = Path(sess["staging_dir"]) if sess.get("staging_dir") else (tmp_path / "stg")
    staging.mkdir(parents=True, exist_ok=True)

    # Also ensure staging_dir is set in the DB
    if not sess.get("staging_dir"):
        db_row = (
            await db_session.execute(select(ImportSession).where(ImportSession.id == sid))
        ).scalar_one()
        db_row.staging_dir = str(staging)
        await db_session.flush()

    img_file = staging / "photo.jpg"
    img_file.write_bytes(b"\xff\xd8\xff")

    img = await _add_image(
        db_session, sid, str(img_file), order=0, is_default=False, is_url=False
    )

    resp = await client.delete(
        f"/api/import-sessions/{sid}/images/{img.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert not img_file.exists()


@pytest.mark.asyncio
async def test_delete_session_image_404_on_wrong_session(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """404 when image_id belongs to a different session."""
    csrf, _uid = await _setup_and_login(client)
    sess_a = await _create_session_via_api(client, csrf)
    sess_b = await _create_session_via_api(client, csrf)

    img = await _add_image(
        db_session, uuid.UUID(sess_b["id"]), "http://example.com/z.jpg", order=0
    )

    resp = await client.delete(
        f"/api/import-sessions/{sess_a['id']}/images/{img.id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# C. PATCH default_image_path / commit default image (issue #14)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_default_image_path_syncs_is_default(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """PATCH default_image_path to a non-first image syncs is_default on all rows.

    Regression guard for issue #14: the PATCH handler must update
    ImportSessionImage.is_default so the commit handler sees the correct default.
    """
    csrf, _uid = await _setup_and_login(client)
    sess = await _create_session_via_api(client, csrf)
    sid = uuid.UUID(sess["id"])

    # First image starts as default; second is not.
    img_a = await _add_image(
        db_session, sid, "https://example.com/first.jpg", order=0, is_default=True
    )
    img_b = await _add_image(
        db_session, sid, "https://example.com/second.jpg", order=1, is_default=False
    )

    # PATCH to make the second image the default.
    resp = await client.patch(
        f"/api/import-sessions/{sid}",
        json={"default_image_path": "https://example.com/second.jpg"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_image_path"] == "https://example.com/second.jpg"

    # DB rows must reflect the new is_default state.
    await db_session.refresh(img_a)
    await db_session.refresh(img_b)
    assert img_b.is_default is True, "Second image should now be is_default=True"
    assert img_a.is_default is False, "First image should now be is_default=False"


@pytest.mark.asyncio
async def test_commit_honors_patched_default_image(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Committing after PATCH default_image_path uses the user-selected image.

    Regression guard for issue #14: the committed Item's default Image must be
    the one the user selected in the wizard, NOT the first image in the list.
    """
    from app.models.image import Image  # noqa: PLC0415
    from app.models.import_session import ImportSessionStatus  # noqa: PLC0415

    csrf, _uid = await _setup_and_login(client)

    # Create library.
    lib_path = tmp_path / "lib"
    lib_path.mkdir()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Default Image Test Lib", "mount_path": str(lib_path)},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    library_id = lib_resp.json()["id"]

    # Create an upload session then advance to pending_wizard via DB.
    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    session_id = uuid.UUID(create_resp.json()["id"])

    res = await db_session.execute(
        select(ImportSession).where(ImportSession.id == session_id)
    )
    sess = res.scalar_one()
    sess.status = ImportSessionStatus.pending_wizard
    sess.confirmed_title = "Default Image Test Item"
    sess.library_id = library_id
    await db_session.flush()

    # Two URL images; first is default initially.
    img_a = ImportSessionImage(
        session_id=session_id,
        path="https://example.com/first.jpg",
        is_url=True,
        source="scrape",
        order=0,
        is_default=True,
    )
    img_b = ImportSessionImage(
        session_id=session_id,
        path="https://example.com/second.jpg",
        is_url=True,
        source="scrape",
        order=1,
        is_default=False,
    )
    db_session.add(img_a)
    db_session.add(img_b)
    await db_session.flush()

    # User picks the second image as default via the wizard.
    patch_resp = await client.patch(
        f"/api/import-sessions/{session_id}",
        json={"default_image_path": "https://example.com/second.jpg"},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_resp.status_code == 200

    # Mock httpx so both URL fetches succeed.
    fake_bytes = b"\xff\xd8\xff\xe0"  # minimal JFIF header

    def _make_mock_client(*args: object, **kwargs: object) -> MagicMock:  # type: ignore[return]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = fake_bytes
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)
        return mock_client

    with patch("httpx.Client", side_effect=_make_mock_client):
        commit_resp = await client.post(
            f"/api/import-sessions/{session_id}/commit",
            headers={"X-CSRF-Token": csrf},
        )

    assert commit_resp.status_code == 200, commit_resp.text
    item_id = commit_resp.json()["item_id"]

    # The second image (order=1) must be the default Image on the committed Item.
    img_res = await db_session.execute(
        select(Image).where(Image.item_id == item_id).order_by(Image.order)
    )
    images = img_res.scalars().all()
    assert len(images) == 2, f"Expected 2 Image rows, got {len(images)}"

    default_imgs = [img for img in images if img.is_default]
    assert len(default_imgs) == 1, (
        f"Expected exactly 1 default Image, got {len(default_imgs)}"
    )
    assert default_imgs[0].order == 1, (
        f"Expected 2nd image (order=1) to be default; got order={default_imgs[0].order}. "
        "This is issue #14: the PATCH-selected default was not applied on commit."
    )


@pytest.mark.asyncio
async def test_commit_fallback_honors_default_image_path(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Commit fallback: default_image_path is honored even if is_default flags are unset.

    Edge case: PATCH set default_image_path before images were materialized,
    so no ImportSessionImage row has is_default=True.  The commit handler must
    still select the correct image as default via the fallback path.
    """
    from app.models.image import Image  # noqa: PLC0415
    from app.models.import_session import ImportSessionStatus  # noqa: PLC0415

    csrf, _uid = await _setup_and_login(client)

    lib_path = tmp_path / "lib"
    lib_path.mkdir()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Fallback Test Lib", "mount_path": str(lib_path)},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    library_id = lib_resp.json()["id"]

    create_resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_resp.status_code == 201
    session_id = uuid.UUID(create_resp.json()["id"])

    # Manually set up session: pending_wizard, default_image_path points to
    # second image, but neither image has is_default=True.
    res = await db_session.execute(
        select(ImportSession).where(ImportSession.id == session_id)
    )
    sess = res.scalar_one()
    sess.status = ImportSessionStatus.pending_wizard
    sess.confirmed_title = "Fallback Default Test Item"
    sess.library_id = library_id
    sess.default_image_path = "https://example.com/second.jpg"
    await db_session.flush()

    # Both images have is_default=False — simulates the edge case.
    img_a = ImportSessionImage(
        session_id=session_id,
        path="https://example.com/first.jpg",
        is_url=True,
        source="scrape",
        order=0,
        is_default=False,
    )
    img_b = ImportSessionImage(
        session_id=session_id,
        path="https://example.com/second.jpg",
        is_url=True,
        source="scrape",
        order=1,
        is_default=False,
    )
    db_session.add(img_a)
    db_session.add(img_b)
    await db_session.flush()

    fake_bytes = b"\xff\xd8\xff\xe0"

    def _make_mock_client(*args: object, **kwargs: object) -> MagicMock:  # type: ignore[return]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = fake_bytes
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)
        return mock_client

    with patch("httpx.Client", side_effect=_make_mock_client):
        commit_resp = await client.post(
            f"/api/import-sessions/{session_id}/commit",
            headers={"X-CSRF-Token": csrf},
        )

    assert commit_resp.status_code == 200, commit_resp.text
    item_id = commit_resp.json()["item_id"]

    img_res = await db_session.execute(
        select(Image).where(Image.item_id == item_id).order_by(Image.order)
    )
    images = img_res.scalars().all()
    assert len(images) == 2

    default_imgs = [img for img in images if img.is_default]
    assert len(default_imgs) == 1, (
        f"Expected exactly 1 default Image, got {len(default_imgs)}"
    )
    assert default_imgs[0].order == 1, (
        f"Expected 2nd image (order=1) to be default via fallback; "
        f"got order={default_imgs[0].order}"
    )


@pytest.mark.asyncio
async def test_delete_session_image_404_on_missing_image(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """404 when image_id doesn't exist at all."""
    csrf, _uid = await _setup_and_login(client)
    sess = await _create_session_via_api(client, csrf)

    resp = await client.delete(
        f"/api/import-sessions/{sess['id']}/images/999999",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404
