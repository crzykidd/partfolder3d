"""Tests for backend/app/worker/threemf.py — 3MF slicer reader.

Uses small in-memory ZIP archives built with the zipfile module; no real
3MF files are required.  All tests are pure-Python / lxml — no trimesh,
no GL, no DB.

Scenarios:
  - Sliced 3MF with slice_info + project_settings + thumbnail → full metadata
  - Unsliced 3MF (standard, no Bambu extensions) → sliced=False, minimal fields
  - Gcode entry detection (alternative sliced signal)
  - Thumbnail priority: plate_1.png preferred over thumbnail.png
  - Multiple plates: per-plate aggregation
  - Malformed files: not-a-zip, corrupt XML, missing ZIP entries → no crash
  - Missing lxml: graceful degradation (only when lxml not available; skip if present)
"""

from __future__ import annotations  # noqa: I001

import io
import json
import zipfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_3mf(
    files: dict[str, bytes],
) -> bytes:
    """Build a minimal .3mf ZIP from a dict of {entry_name: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Minimal 3MF structure
        zf.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


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
        <triangles>
          <triangle v1="0" v2="1" v3="2"/>
        </triangles>
      </mesh>
    </object>
  </resources>
  <build><item objectid="1"/></build>
</model>"""

_SLICE_INFO_ONE_PLATE = b"""<?xml version="1.0" encoding="utf-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="prediction" value="3600"/>
    <metadata key="weight" value="25.5"/>
    <filament id="1" type="PLA" color="#FF0000" used_m="10.5" used_g="12.3"/>
    <filament id="2" type="PETG" color="#00FF00" used_m="5.2" used_g="6.1"/>
  </plate>
</config>"""

_SLICE_INFO_TWO_PLATES = b"""<?xml version="1.0" encoding="utf-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="prediction" value="1800"/>
    <metadata key="weight" value="10.0"/>
    <filament id="1" type="PLA" color="#FF0000" used_m="5.0" used_g="6.0"/>
  </plate>
  <plate>
    <metadata key="index" value="2"/>
    <metadata key="prediction" value="2700"/>
    <metadata key="weight" value="15.0"/>
    <filament id="1" type="PLA" color="#FF0000" used_m="7.5" used_g="9.0"/>
  </plate>
</config>"""

_PROJECT_SETTINGS = json.dumps({
    "printer_model": "Bambu Lab X1C",
    "version": "01.09.05.52",
    "filament_colour": ["#FF0000", "#00FF00"],
    "filament_type": ["PLA", "PETG"],
}).encode()

# A tiny 1×1 white PNG (minimal valid PNG bytes)
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"  # PNG signature
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
    b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sliced_3mf_full_metadata(tmp_path: Path) -> None:
    """Sliced 3MF returns correct plate count, filament data, print time, thumbnail."""
    from app.worker.threemf import read_3mf

    content = _make_3mf({
        "3D/3dmodel.model": _MINIMAL_3DMODEL,
        "Metadata/plate_1.gcode": b"G28 ; home\nG1 Z5\n",
        "Metadata/plate_1.png": _TINY_PNG,
        "Metadata/slice_info.config": _SLICE_INFO_ONE_PLATE,
        "Metadata/project_settings.config": _PROJECT_SETTINGS,
    })
    p = tmp_path / "test.3mf"
    p.write_bytes(content)

    info = read_3mf(p)

    assert info["sliced"] is True
    assert info["thumbnail_bytes"] == _TINY_PNG
    assert info["thumbnail_entry"] is not None
    assert "plate_1.png" in info["thumbnail_entry"].lower()

    assert info["plate_count"] == 1
    assert info["print_time_s"] == 3600
    assert info["total_filament_g"] == pytest.approx(18.4, abs=0.01)  # 12.3 + 6.1

    filaments = info["filament"]
    assert len(filaments) == 2
    slots = {f["slot"] for f in filaments}
    assert slots == {1, 2}

    fil1 = next(f for f in filaments if f["slot"] == 1)
    assert fil1["type"] == "PLA"
    assert fil1["color_hex"] == "#FF0000"
    assert fil1["used_m"] == pytest.approx(10.5)
    assert fil1["used_g"] == pytest.approx(12.3)

    fil2 = next(f for f in filaments if f["slot"] == 2)
    assert fil2["type"] == "PETG"
    assert fil2["color_hex"] == "#00FF00"

    assert info["printer_model"] == "Bambu Lab X1C"
    assert info["objects_total"] == 1  # from 3dmodel.model


def test_two_plate_aggregation(tmp_path: Path) -> None:
    """Multi-plate 3MF: print time and filament weight aggregated across plates."""
    from app.worker.threemf import read_3mf

    content = _make_3mf({
        "3D/3dmodel.model": _MINIMAL_3DMODEL,
        "Metadata/plate_1.gcode": b"G28\n",
        "Metadata/plate_2.gcode": b"G28\n",
        "Metadata/slice_info.config": _SLICE_INFO_TWO_PLATES,
    })
    p = tmp_path / "two_plate.3mf"
    p.write_bytes(content)

    info = read_3mf(p)

    assert info["sliced"] is True
    assert info["plate_count"] == 2
    # Total time: 1800 + 2700 = 4500
    assert info["print_time_s"] == 4500
    # Slot 1 appears in both plates; last one's used_g wins: 9.0
    # total_filament_g = sum of used_g across all filaments after dedup
    # Dedup by slot (last plate wins for used_g): slot 1 → 9.0
    assert info["total_filament_g"] == pytest.approx(9.0)


def test_unsliced_3mf(tmp_path: Path) -> None:
    """Standard (non-Bambu) 3MF without gcode → sliced=False, no slicer metadata."""
    from app.worker.threemf import read_3mf

    content = _make_3mf({
        "3D/3dmodel.model": _MINIMAL_3DMODEL,
    })
    p = tmp_path / "unsliced.3mf"
    p.write_bytes(content)

    info = read_3mf(p)

    assert info["sliced"] is False
    assert info["print_time_s"] is None
    assert info["total_filament_g"] is None
    assert info["filament"] == []
    assert info["plates"] == []
    assert info["thumbnail_bytes"] is None


def test_thumbnail_priority(tmp_path: Path) -> None:
    """plate_1.png is preferred over thumbnail.png when both exist."""
    from app.worker.threemf import read_3mf

    plate_png = _TINY_PNG + b"PLATE"
    generic_png = _TINY_PNG + b"GENERIC"

    content = _make_3mf({
        "Metadata/plate_1.png": plate_png,
        "Metadata/thumbnail.png": generic_png,
    })
    p = tmp_path / "thumb_priority.3mf"
    p.write_bytes(content)

    info = read_3mf(p)
    assert info["thumbnail_bytes"] == plate_png
    assert info["thumbnail_entry"] is not None
    assert "plate_1" in info["thumbnail_entry"].lower()


def test_thumbnail_fallback(tmp_path: Path) -> None:
    """Falls back to thumbnail.png when plate_1.png is absent."""
    from app.worker.threemf import read_3mf

    content = _make_3mf({
        "Metadata/thumbnail.png": _TINY_PNG,
    })
    p = tmp_path / "thumb_fallback.3mf"
    p.write_bytes(content)

    info = read_3mf(p)
    assert info["thumbnail_bytes"] == _TINY_PNG
    assert info["thumbnail_entry"] is not None
    assert "thumbnail" in info["thumbnail_entry"].lower()


def test_gcode_sliced_detection(tmp_path: Path) -> None:
    """plate_*.gcode entry (no slice_info) still signals sliced=True."""
    from app.worker.threemf import read_3mf

    content = _make_3mf({
        "Metadata/plate_2.gcode": b"G28\n",
    })
    p = tmp_path / "gcode_only.3mf"
    p.write_bytes(content)

    info = read_3mf(p)
    assert info["sliced"] is True


def test_not_a_zip(tmp_path: Path) -> None:
    """Corrupted / non-ZIP file returns safe defaults without raising."""
    from app.worker.threemf import read_3mf

    p = tmp_path / "bad.3mf"
    p.write_bytes(b"THIS IS NOT A ZIP FILE AT ALL")

    info = read_3mf(p)

    assert info["sliced"] is False
    assert info["thumbnail_bytes"] is None
    assert info["filament"] == []


def test_missing_file(tmp_path: Path) -> None:
    """Missing file path returns safe defaults without raising."""
    from app.worker.threemf import read_3mf

    p = tmp_path / "nonexistent.3mf"
    # Don't write anything

    info = read_3mf(p)

    assert info["sliced"] is False
    assert info["thumbnail_bytes"] is None


def test_corrupt_slice_info_xml(tmp_path: Path) -> None:
    """Malformed slice_info.config XML: no crash, sliced still detected via gcode."""
    from app.worker.threemf import read_3mf

    content = _make_3mf({
        "Metadata/plate_1.gcode": b"G28\n",
        "Metadata/slice_info.config": b"NOT VALID XML <<<",
    })
    p = tmp_path / "corrupt_slice.3mf"
    p.write_bytes(content)

    info = read_3mf(p)
    # Gcode still signals sliced; XML parse failure is handled gracefully
    assert info["sliced"] is True
    assert info["plates"] == []   # XML failed → no plates parsed
    assert info["filament"] == []


def test_project_settings_enriches_filament_colors(tmp_path: Path) -> None:
    """Colors from project_settings.config fill in missing slice_info colors."""
    from app.worker.threemf import read_3mf

    # slice_info without colors (color attribute missing)
    slice_no_color = b"""<?xml version="1.0" encoding="utf-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="prediction" value="1000"/>
    <metadata key="weight" value="5.0"/>
    <filament id="1" type="ABS" used_m="3.0" used_g="4.0"/>
  </plate>
</config>"""

    proj = json.dumps({
        "filament_colour": ["#AABBCC"],
        "filament_type": ["ABS"],
    }).encode()

    content = _make_3mf({
        "Metadata/plate_1.gcode": b"G28\n",
        "Metadata/slice_info.config": slice_no_color,
        "Metadata/project_settings.config": proj,
    })
    p = tmp_path / "color_enrich.3mf"
    p.write_bytes(content)

    info = read_3mf(p)

    assert info["sliced"] is True
    assert len(info["filament"]) == 1
    fil = info["filament"][0]
    # Color should be filled from project_settings (slot 1 → index 0)
    assert fil["color_hex"] == "#AABBCC"
    assert fil["type"] == "ABS"


def test_return_schema_completeness(tmp_path: Path) -> None:
    """All required keys are present in the return dict."""
    from app.worker.threemf import read_3mf

    content = _make_3mf({})
    p = tmp_path / "empty.3mf"
    p.write_bytes(content)

    info = read_3mf(p)

    required_keys = {
        "thumbnail_bytes", "thumbnail_entry", "sliced", "slicer",
        "printer_model", "plate_count", "objects_total", "print_time_s",
        "total_filament_g", "filament", "plates",
    }
    assert required_keys == set(info.keys())
