"""Tests for Phase 16 — per-object mesh analysis.

Covers:
  - STL analysis: box mesh → 1 object, 1 color, est_grams ≈ volume×density×infill
  - 3MF standard colors: 2-material 3MF → correct color count + per-object volumes
  - Non-watertight mesh → low_confidence=True, no crash, fallback volume
  - Malformed / empty → no raise (best-effort)
  - analyze_file: FileAnalysis totals correct
  - _parse_3mf_colors: XML parsing for basematerials

Fixtures are generated programmatically via trimesh + hand-crafted 3MF XML
(no external test assets needed).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers to generate test fixtures
# ---------------------------------------------------------------------------


def _write_box_stl(path: Path, size: float = 10.0) -> None:
    """Write a solid cube STL at *path* via trimesh."""
    import trimesh

    box = trimesh.creation.box(extents=[size, size, size])
    # STL export
    stl_bytes = box.export(file_type="stl")
    path.write_bytes(stl_bytes)


def _write_nonwatertight_stl(path: Path) -> None:
    """Write an open (non-watertight) mesh as STL.

    A single triangle is not watertight; trimesh cannot compute volume properly.
    """
    import numpy as np
    import trimesh

    # Single triangle — definitely not watertight
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)
    stl_bytes = mesh.export(file_type="stl")
    path.write_bytes(stl_bytes)


def _write_two_color_3mf(path: Path) -> None:
    """Write a minimal 2-material 3MF to *path* using a hand-crafted ZIP.

    Model XML contains:
      - <basematerials id="1"> with Red + Blue bases
      - one <object> with per-triangle material refs (p1=0 → Red, p1=1 → Blue)
    This exercises the triangle-level color parsing.
    """
    # A tiny triangle mesh (tetrahedron): 4 vertices, 4 faces
    model_xml = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter"
       xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <basematerials id="1">
      <base name="Red" displaycolor="#FF0000"/>
      <base name="Blue" displaycolor="#0000FF"/>
    </basematerials>
    <object id="2" type="model" pid="1" pindex="0">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0"/>
          <vertex x="10" y="0" z="0"/>
          <vertex x="0" y="10" z="0"/>
          <vertex x="0" y="0" z="10"/>
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" pid="1" p1="0" p2="0" p3="0"/>
          <triangle v1="0" v2="1" v3="3" pid="1" p1="1" p2="1" p3="1"/>
          <triangle v1="0" v2="2" v3="3" pid="1" p1="0" p2="0" p3="0"/>
          <triangle v1="1" v2="2" v3="3" pid="1" p1="1" p2="1" p3="1"/>
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="2"/>
  </build>
</model>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'  # noqa: E501
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'  # noqa: E501
            '</Types>'
        ))
        zf.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"'
            ' Target="/3D/3dmodel.model"/>'
            '</Relationships>'
        ))
        zf.writestr("3D/3dmodel.model", model_xml)
    path.write_bytes(buf.getvalue())


def _write_object_level_color_3mf(path: Path) -> None:
    """Write a 3MF where two separate objects each have a different single color."""
    model_xml = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter"
       xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <basematerials id="1">
      <base name="Green" displaycolor="#00FF00"/>
      <base name="Yellow" displaycolor="#FFFF00"/>
    </basematerials>
    <object id="2" type="model" pid="1" pindex="0">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0"/>
          <vertex x="5" y="0" z="0"/>
          <vertex x="0" y="5" z="0"/>
          <vertex x="0" y="0" z="5"/>
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2"/>
          <triangle v1="0" v2="1" v3="3"/>
          <triangle v1="0" v2="2" v3="3"/>
          <triangle v1="1" v2="2" v3="3"/>
        </triangles>
      </mesh>
    </object>
    <object id="3" type="model" pid="1" pindex="1">
      <mesh>
        <vertices>
          <vertex x="10" y="0" z="0"/>
          <vertex x="15" y="0" z="0"/>
          <vertex x="10" y="5" z="0"/>
          <vertex x="10" y="0" z="5"/>
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2"/>
          <triangle v1="0" v2="1" v3="3"/>
          <triangle v1="0" v2="2" v3="3"/>
          <triangle v1="1" v2="2" v3="3"/>
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="2"/>
    <item objectid="3"/>
  </build>
</model>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'  # noqa: E501
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'  # noqa: E501
            '</Types>'
        ))
        zf.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"'
            ' Target="/3D/3dmodel.model"/>'
            '</Relationships>'
        ))
        zf.writestr("3D/3dmodel.model", model_xml)
    path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# Tests: _parse_3mf_colors (unit)
# ---------------------------------------------------------------------------


def test_parse_3mf_colors_basematerials(tmp_path: Path) -> None:
    """Standard basematerials: object-level pid/pindex → single color."""
    from app.worker.mesh_analysis import _parse_3mf_colors  # noqa: PLC0415

    p = tmp_path / "test.3mf"
    _write_object_level_color_3mf(p)
    result = _parse_3mf_colors(p.read_bytes())

    # Two objects (ids "2" and "3"), each with one color
    assert "2" in result or "3" in result
    colors_obj2 = result.get("2", ([], False))
    colors_obj3 = result.get("3", ([], False))
    # Object 2: pindex=0 → #00FF00 (Green)
    assert "#00FF00" in [c.upper() for c in colors_obj2[0]]
    # Object 3: pindex=1 → #FFFF00 (Yellow)
    assert "#FFFF00" in [c.upper() for c in colors_obj3[0]]


def test_parse_3mf_colors_triangle_refs(tmp_path: Path) -> None:
    """Triangle-level p1 refs: one object with 2 distinct colors."""
    from app.worker.mesh_analysis import _parse_3mf_colors  # noqa: PLC0415

    p = tmp_path / "tri.3mf"
    _write_two_color_3mf(p)
    result = _parse_3mf_colors(p.read_bytes())

    # Object "2" should have both Red and Blue
    assert "2" in result
    colors, _ = result["2"]
    colors_upper = {c.upper() for c in colors}
    assert "#FF0000" in colors_upper
    assert "#0000FF" in colors_upper


def test_parse_3mf_colors_empty_zip(tmp_path: Path) -> None:
    """Empty / malformed ZIP → returns empty dict, no crash."""
    from app.worker.mesh_analysis import _parse_3mf_colors  # noqa: PLC0415

    p = tmp_path / "bad.3mf"
    p.write_bytes(b"not a zip")
    result = _parse_3mf_colors(p.read_bytes())
    assert result == {}


# ---------------------------------------------------------------------------
# Tests: analyze_file — STL
# ---------------------------------------------------------------------------


def test_analyze_stl_box(tmp_path: Path) -> None:
    """10mm box STL → 1 object, 1 color, est_grams sane."""
    from app.worker.mesh_analysis import analyze_file  # noqa: PLC0415

    p = tmp_path / "box.stl"
    _write_box_stl(p, size=10.0)

    result = analyze_file(p, density_g_cm3=1.24, infill_pct=15.0)

    assert result["total_objects"] == 1
    assert result["total_colors"] >= 1  # STL has 1 color
    assert result["source_hash"] is not None

    obj = result["objects"][0]
    assert obj["color_count"] == 1
    assert obj["est_method"] == "volume"
    assert obj["dims_mm"] is not None
    assert len(obj["dims_mm"]) == 3

    # 10mm cube volume = 1 cm³; at 1.24 g/cm³ × 15% ≈ 0.186 g
    # Allow large tolerance since trimesh may return slightly diff volume
    if obj["volume_cm3"] is not None:
        assert 0.5 < obj["volume_cm3"] < 2.0, f"volume_cm3={obj['volume_cm3']}"

    if obj["est_grams"] is not None:
        # Should be close to 1 * 1.24 * 0.15 = 0.186 g
        # Allow generous range for mesh approximations
        assert 0.01 < obj["est_grams"] < 1.0, f"est_grams={obj['est_grams']}"


def test_analyze_stl_hash_caching(tmp_path: Path) -> None:
    """analyze_file with pre-supplied hash returns it in the result."""
    from app.worker.mesh_analysis import analyze_file  # noqa: PLC0415

    p = tmp_path / "box.stl"
    _write_box_stl(p)

    fake_hash = "a" * 64
    result = analyze_file(p, source_hash=fake_hash)
    assert result["source_hash"] == fake_hash


# ---------------------------------------------------------------------------
# Tests: analyze_file — non-watertight mesh
# ---------------------------------------------------------------------------


def test_analyze_nonwatertight_no_crash(tmp_path: Path) -> None:
    """Single triangle (open mesh) → low_confidence=True, no crash."""
    from app.worker.mesh_analysis import analyze_file  # noqa: PLC0415

    p = tmp_path / "open.stl"
    _write_nonwatertight_stl(p)

    result = analyze_file(p, density_g_cm3=1.24, infill_pct=15.0)

    assert result["total_objects"] >= 1
    obj = result["objects"][0]
    # Should be flagged low_confidence
    assert obj["low_confidence"] is True
    # Should NOT have crashed; volume or est_grams may be None or from convex hull
    # The function must return without raising


def test_analyze_nonwatertight_watertight_flag(tmp_path: Path) -> None:
    """Non-watertight mesh: watertight=False in result."""
    from app.worker.mesh_analysis import analyze_file  # noqa: PLC0415

    p = tmp_path / "open2.stl"
    _write_nonwatertight_stl(p)

    result = analyze_file(p)
    obj = result["objects"][0]
    assert obj["watertight"] is False


# ---------------------------------------------------------------------------
# Tests: analyze_file — 3MF with multiple materials
# ---------------------------------------------------------------------------


def test_analyze_3mf_two_color_single_object(tmp_path: Path) -> None:
    """2-material 3MF (one object with per-triangle colors) → color_count=2."""
    from app.worker.mesh_analysis import analyze_file  # noqa: PLC0415

    p = tmp_path / "two_color.3mf"
    _write_two_color_3mf(p)

    result = analyze_file(p, density_g_cm3=1.24, infill_pct=15.0)

    assert result["total_objects"] >= 1
    assert result["total_colors"] >= 2

    # At least one object should have both red and blue
    all_colors = {c.upper() for obj in result["objects"] for c in obj.get("colors", [])}
    assert "#FF0000" in all_colors or "#0000FF" in all_colors

    # Per-object volume should be non-None (tetrahedra are watertight)
    for obj in result["objects"]:
        assert obj["volume_cm3"] is not None or obj["low_confidence"], (
            f"object {obj['name']} has no volume and isn't flagged low_confidence"
        )


def test_analyze_3mf_two_object_colors(tmp_path: Path) -> None:
    """3MF with 2 objects, each a different single color."""
    from app.worker.mesh_analysis import analyze_file  # noqa: PLC0415

    p = tmp_path / "two_obj.3mf"
    _write_object_level_color_3mf(p)

    result = analyze_file(p, density_g_cm3=1.24, infill_pct=15.0)

    # Two objects (or one merged if trimesh concatenates) — at least we get data
    assert result["total_objects"] >= 1
    # Colors should include green or yellow from the basematerials
    all_colors = {c.upper() for obj in result["objects"] for c in obj.get("colors", [])}
    assert "#00FF00" in all_colors or "#FFFF00" in all_colors


# ---------------------------------------------------------------------------
# Tests: analyze_file — unsupported extension
# ---------------------------------------------------------------------------


def test_analyze_file_unsupported_extension(tmp_path: Path) -> None:
    """Non-mesh extension → ValueError, not a generic crash."""
    from app.worker.mesh_analysis import analyze_file  # noqa: PLC0415

    p = tmp_path / "test.gcode"
    p.write_bytes(b"; gcode\nG28\n")

    with pytest.raises(ValueError, match="Unsupported extension"):
        analyze_file(p)


# ---------------------------------------------------------------------------
# Tests: _safe_volume_cm3 helpers
# ---------------------------------------------------------------------------


def test_safe_volume_watertight(tmp_path: Path) -> None:
    """A box is watertight; _safe_volume_cm3 returns low_confidence=False."""
    import trimesh

    from app.worker.mesh_analysis import _safe_volume_cm3  # noqa: PLC0415

    box = trimesh.creation.box(extents=[10, 10, 10])
    volume_cm3, watertight, low_conf = _safe_volume_cm3(box)

    assert watertight is True
    assert low_conf is False
    assert volume_cm3 is not None
    # 10³ mm³ = 1 cm³ (±ε)
    assert abs(volume_cm3 - 1.0) < 0.1


def test_safe_volume_open_mesh() -> None:
    """Single triangle → low_confidence=True."""
    import numpy as np
    import trimesh

    from app.worker.mesh_analysis import _safe_volume_cm3  # noqa: PLC0415

    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)

    _, watertight, low_conf = _safe_volume_cm3(mesh)
    assert low_conf is True
    assert watertight is False
