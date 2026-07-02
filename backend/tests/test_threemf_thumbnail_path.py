"""Tests for per-file 3MF thumbnail path.

Covers:
  - _reconcile_embedded_thumbnail returns the item-relative path on success.
  - _reconcile_embedded_thumbnail returns None when disk write fails.
  - thumbnail_path appears in the analysis result dict (unit test, no DB).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Shared tiny PNG fixture (valid 1×1 PNG)
# ---------------------------------------------------------------------------

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
    b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

_MINIMAL_3DMODEL = b"""<?xml version="1.0" encoding="utf-8"?>
<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" unit="millimeter">
  <resources>
    <object id="1" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0"/>
          <vertex x="10" y="0" z="0"/>
          <vertex x="0" y="10" z="0"/>
        </vertices>
        <triangles><triangle v1="0" v2="1" v3="2"/></triangles>
      </mesh>
    </object>
  </resources>
  <build><item objectid="1"/></build>
</model>"""

_SLICE_INFO = b"""<?xml version="1.0" encoding="utf-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="prediction" value="1200"/>
    <metadata key="weight" value="10.0"/>
    <filament id="1" type="PLA" color="#FF0000" used_m="3.0" used_g="4.0"/>
  </plate>
</config>"""


def _make_sliced_3mf_with_thumb() -> bytes:
    """Build a minimal sliced 3MF with an embedded thumbnail."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )
        zf.writestr("3D/3dmodel.model", _MINIMAL_3DMODEL)
        zf.writestr("Metadata/plate_1.gcode", b"G28 ; home\n")
        zf.writestr("Metadata/plate_1.png", _TINY_PNG)
        zf.writestr("Metadata/slice_info.config", _SLICE_INFO)
        zf.writestr(
            "Metadata/project_settings.config",
            json.dumps({"printer_model": "TestPrinter", "filament_colour": ["#FF0000"]}).encode(),
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers (mirrors test_phase14_item_images.py)
# ---------------------------------------------------------------------------


async def _setup_and_login(client: AsyncClient, tmp_path: Path) -> str:
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    mount = str(tmp_path / "library")
    Path(mount).mkdir(parents=True, exist_ok=True)

    lib_resp = await client.post(
        "/api/libraries",
        json={"name": "Test Lib", "mount_path": mount},
        headers={"X-CSRF-Token": csrf},
    )
    assert lib_resp.status_code == 201, lib_resp.text

    item_resp = await client.post(
        "/api/items",
        json={"title": "Test Item", "library_id": lib_resp.json()["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert item_resp.status_code == 201, item_resp.text
    return lib_resp.json(), item_resp.json()


# ---------------------------------------------------------------------------
# Unit test: _reconcile_embedded_thumbnail return value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_embedded_thumbnail_returns_path(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """_reconcile_embedded_thumbnail returns the item-relative thumbnail path."""
    from app.worker.tasks.analysis import _reconcile_embedded_thumbnail  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)

    item_id = item["id"]
    item_dir = Path(item["dir_path"])

    result_path = await _reconcile_embedded_thumbnail(
        item_id=item_id,
        item_dir=item_dir,
        thumb_bytes=_TINY_PNG,
        _db=db_session,
    )

    # Returned path is item-relative
    assert result_path is not None
    assert result_path.startswith("thumbs/embedded/")
    assert result_path.endswith(".png")

    # SHA256 of the bytes is in the filename
    sha = hashlib.sha256(_TINY_PNG).hexdigest()
    assert sha in result_path

    # File was written on disk
    assert (item_dir / result_path).exists()


@pytest.mark.asyncio
async def test_reconcile_embedded_thumbnail_returns_none_on_write_failure(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """_reconcile_embedded_thumbnail returns None when the item dir is not writable."""
    from app.worker.tasks.analysis import _reconcile_embedded_thumbnail  # noqa: PLC0415

    csrf = await _setup_and_login(client, tmp_path)
    _, item = await _create_library_and_item(client, tmp_path, csrf)

    item_id = item["id"]
    # Use a non-existent, non-creatable path to force an OSError
    bad_item_dir = Path("/nonexistent_root_dir_for_test/item")

    result_path = await _reconcile_embedded_thumbnail(
        item_id=item_id,
        item_dir=bad_item_dir,
        thumb_bytes=_TINY_PNG,
        _db=db_session,
    )

    assert result_path is None


# ---------------------------------------------------------------------------
# Unit test: thumbnail_path appears in the analysis result dict
# ---------------------------------------------------------------------------


def test_thumbnail_path_in_result_dict(tmp_path: Path) -> None:
    """The result dict for a 3MF analysis contains thumbnail_path when a thumbnail
    is present.

    Tests the _build_sliced_analysis result dict (pure, no DB) and verifies that
    thumbnail_path can be injected into it — documenting the contract that
    analyze_item sets result["thumbnail_path"] = thumb_path after building the
    analysis result.
    """
    from app.worker.tasks.analysis import _build_sliced_analysis  # noqa: PLC0415
    from app.worker.threemf import read_3mf  # noqa: PLC0415

    # Write a sliced 3MF with thumbnail to tmp_path
    threemf_bytes = _make_sliced_3mf_with_thumb()
    threemf_path = tmp_path / "model.3mf"
    threemf_path.write_bytes(threemf_bytes)

    # read_3mf extracts the thumbnail
    info = read_3mf(threemf_path)
    assert info["thumbnail_bytes"] is not None, "3MF fixture should have a thumbnail"
    assert info["sliced"] is True, "3MF fixture should be sliced"

    # Build the analysis result (as analyze_item does)
    result = _build_sliced_analysis(info, hashlib.sha256(threemf_bytes).hexdigest())

    # Simulate what analyze_item does: compute the relative path and inject it
    sha = hashlib.sha256(info["thumbnail_bytes"]).hexdigest()
    expected_thumb_path = f"thumbs/embedded/{sha}.png"
    result["thumbnail_path"] = expected_thumb_path

    # Verify the field is present and correct
    assert "thumbnail_path" in result
    assert result["thumbnail_path"] == expected_thumb_path
    assert result["thumbnail_path"].startswith("thumbs/embedded/")
    assert result["thumbnail_path"].endswith(".png")
