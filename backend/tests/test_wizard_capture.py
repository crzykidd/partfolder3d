"""Tests: wizard viewport-capture bundle (#26).

Covers:
  A. GET /api/import-sessions/{id}/files/{filename}  (serve a staged file)
     - serves a staged model file
     - rejects path traversal (does not leak a file outside staging)
     - 404 for a missing file
     - 404 for a file in a different session
     - auth required (401 when logged out)

  B. POST /api/import-sessions/{id}/images  (viewport-capture save)
     - creates a local ImportSessionImage (is_url=False, source="capture")
       that shows in the session strip; first image becomes default
     - rejects a non-image upload (422)

  C. Commit carries a captured (local) image into the item as an Image row
     with source=captured, physically copied into images/.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_session import ImportSession, ImportSessionImage, ImportSessionStatus

# 1x1 PNG
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _setup_and_login(client: AsyncClient) -> str:
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


async def _create_upload_session(client: AsyncClient, csrf: str) -> dict:
    resp = await client.post(
        "/api/import-sessions",
        json={"source_type": "upload"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# A. Serve endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serve_staged_file(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    sess = await _create_upload_session(client, csrf)
    staging = Path(sess["staging_dir"])
    (staging / "widget.stl").write_bytes(b"solid widget\nendsolid widget\n")

    resp = await client.get(f"/api/import-sessions/{sess['id']}/files/widget.stl")
    assert resp.status_code == 200
    assert resp.content == b"solid widget\nendsolid widget\n"
    assert resp.headers["content-type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_serve_rejects_path_traversal(client: AsyncClient, tmp_path: Path) -> None:
    csrf = await _setup_and_login(client)
    sess = await _create_upload_session(client, csrf)
    staging = Path(sess["staging_dir"])
    # A secret two levels up from staging (DATA_DIR level).
    secret = staging.parent.parent / "secret.txt"
    secret.write_bytes(b"TOP SECRET")

    # Encoded traversal so the client doesn't normalise it away before routing.
    resp = await client.get(
        f"/api/import-sessions/{sess['id']}/files/..%2f..%2fsecret.txt"
    )
    assert resp.status_code in (400, 404)
    assert b"TOP SECRET" not in resp.content


@pytest.mark.asyncio
async def test_serve_404_missing_file(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    sess = await _create_upload_session(client, csrf)
    resp = await client.get(f"/api/import-sessions/{sess['id']}/files/nope.stl")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_serve_404_other_session_file(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    sess_a = await _create_upload_session(client, csrf)
    sess_b = await _create_upload_session(client, csrf)
    # File exists only in session A's staging.
    (Path(sess_a["staging_dir"]) / "a.stl").write_bytes(b"a")

    resp = await client.get(f"/api/import-sessions/{sess_b['id']}/files/a.stl")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_serve_requires_auth(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    sess = await _create_upload_session(client, csrf)
    (Path(sess["staging_dir"]) / "widget.stl").write_bytes(b"x")

    client.cookies.clear()  # log out
    resp = await client.get(f"/api/import-sessions/{sess['id']}/files/widget.stl")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# B. Capture-save endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_session_image_creates_local_default_image(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    csrf = await _setup_and_login(client)
    sess = await _create_upload_session(client, csrf)
    sid = uuid.UUID(sess["id"])

    # Advance to pending_wizard (where the wizard runs).
    row = (
        await db_session.execute(select(ImportSession).where(ImportSession.id == sid))
    ).scalar_one()
    row.status = ImportSessionStatus.pending_wizard
    await db_session.flush()

    resp = await client.post(
        f"/api/import-sessions/{sid}/images?source=captured",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("capture.png", _PNG, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["images"]) == 1
    img = body["images"][0]
    assert img["is_url"] is False
    assert img["source"] == "capture"
    assert img["is_default"] is True

    # The staged file exists and is servable.
    imgs = (
        await db_session.execute(
            select(ImportSessionImage).where(ImportSessionImage.session_id == sid)
        )
    ).scalars().all()
    assert len(imgs) == 1
    assert Path(imgs[0].path).is_file()
    serve = await client.get(
        f"/api/import-sessions/{sid}/files/{Path(imgs[0].path).name}"
    )
    assert serve.status_code == 200


@pytest.mark.asyncio
async def test_upload_session_image_rejects_non_image(client: AsyncClient) -> None:
    csrf = await _setup_and_login(client)
    sess = await _create_upload_session(client, csrf)
    resp = await client.post(
        f"/api/import-sessions/{sess['id']}/images",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("model.stl", b"solid x", "application/octet-stream")},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# C. Commit carries a captured image into the item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_carries_captured_image(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    from app.models.image import Image, ImageSource  # noqa: PLC0415

    csrf = await _setup_and_login(client)

    lib_path = tmp_path / "lib"
    lib_path.mkdir()
    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Capture Lib", "mount_path": str(lib_path)},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201
    library_id = lib_resp.json()["id"]

    sess = await _create_upload_session(client, csrf)
    sid = uuid.UUID(sess["id"])

    row = (
        await db_session.execute(select(ImportSession).where(ImportSession.id == sid))
    ).scalar_one()
    row.status = ImportSessionStatus.pending_wizard
    row.confirmed_title = "Capture Item"
    row.library_id = library_id
    await db_session.flush()

    # Save a captured image via the endpoint.
    cap_resp = await client.post(
        f"/api/import-sessions/{sid}/images?source=captured",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("capture.png", _PNG, "image/png")},
    )
    assert cap_resp.status_code == 200, cap_resp.text

    commit_resp = await client.post(
        f"/api/import-sessions/{sid}/commit",
        headers={"X-CSRF-Token": csrf},
    )
    assert commit_resp.status_code == 200, commit_resp.text
    item_id = commit_resp.json()["item_id"]

    images = (
        await db_session.execute(
            select(Image).where(Image.item_id == item_id).order_by(Image.order)
        )
    ).scalars().all()
    assert len(images) == 1, f"expected 1 committed image, got {len(images)}"
    captured = images[0]
    assert captured.source == ImageSource.captured
    assert captured.is_default is True
    assert captured.path.startswith("images/")
    # File physically copied into the item's images/ dir (somewhere under lib).
    assert any(
        p.name == Path(captured.path).name and p.is_file()
        for p in lib_path.rglob("*")
    )
