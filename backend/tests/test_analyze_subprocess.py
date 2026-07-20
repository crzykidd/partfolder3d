"""Tests for ``app.worker.analyze_subprocess`` (issue #37 fixes #2 and #4).

Covers the subprocess-isolated mesh analysis runner:
  - A small real mesh fixture analyzed via a real spawned child process
    returns a well-formed FileAnalysis dict (same shape as analyze_file).
  - A tiny max_triangles cap raises AnalyzeCapSkip (fix #4).
  - A near-zero timeout raises AnalyzeTimeout without hanging the parent
    (spawning a fresh interpreter always takes non-zero wall-clock time, so
    timeout_s=0 deterministically trips the timeout path — same pattern used
    for render_subprocess).

These tests spawn REAL child processes (multiprocessing "spawn"), matching
how render_subprocess is exercised in production. No RLIMIT_AS / OOM test is
included here since intentionally exhausting multi-GB of virtual memory in a
test is slow and environment-dependent; the RLIMIT_AS wiring itself is a
straight-line ``resource.setrlimit`` call exercised implicitly by every
successful run below (the child would fail to import trimesh/numpy at all if
the limit were set too low, which none of these tests would tolerate).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _write_box_stl(path: Path, size: float = 10.0) -> None:
    """Write a solid cube STL at *path* via trimesh."""
    import trimesh

    box = trimesh.creation.box(extents=[size, size, size])
    stl_bytes = box.export(file_type="stl")
    path.write_bytes(stl_bytes)


def _write_tiny_3mf(path: Path) -> None:
    """Write a minimal single-object 3MF (tetrahedron, no materials) to *path*."""
    import io
    import zipfile

    model_xml = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter"
       xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="2" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0"/>
          <vertex x="10" y="0" z="0"/>
          <vertex x="0" y="10" z="0"/>
          <vertex x="0" y="0" z="10"/>
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
# Happy path: real subprocess, well-formed result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_analyze_subprocess_returns_well_formed_analysis(tmp_path: Path) -> None:
    """A small real STL analyzed in a spawned child returns a FileAnalysis dict."""
    from app.worker.analyze_subprocess import run_analyze_subprocess  # noqa: PLC0415

    p = tmp_path / "box.stl"
    _write_box_stl(p)

    result = await run_analyze_subprocess(
        p,
        density_g_cm3=1.24,
        infill_pct=15.0,
        source_hash="a" * 64,
        timeout_s=60,
        mem_limit_mb=4096,
        max_triangles=None,
    )

    assert result["source_hash"] == "a" * 64
    assert result["total_objects"] == 1
    assert result["objects"][0]["est_method"] == "volume"
    assert result["objects"][0]["color_count"] == 1
    assert "analyzed_at" in result


# ---------------------------------------------------------------------------
# Cap-skip path (issue #37 fix #4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_analyze_subprocess_cap_skip(tmp_path: Path) -> None:
    """A tiny max_triangles cap on a real mesh → AnalyzeCapSkip, not a crash."""
    from app.worker.analyze_subprocess import (  # noqa: PLC0415
        AnalyzeCapSkip,
        run_analyze_subprocess,
    )

    p = tmp_path / "box.stl"
    _write_box_stl(p)

    with pytest.raises(AnalyzeCapSkip, match="triangles"):
        await run_analyze_subprocess(
            p,
            source_hash="b" * 64,
            timeout_s=60,
            mem_limit_mb=4096,
            max_triangles=1,
        )


# ---------------------------------------------------------------------------
# 3MF pre-load geometry-XML size cap-skip path (issue #37 follow-up)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_analyze_subprocess_3mf_xml_size_cap_skip(tmp_path: Path) -> None:
    """A tiny max_3mf_xml_mb cap on a real 3MF → AnalyzeCapSkip, raised before trimesh.load."""
    from app.worker.analyze_subprocess import (  # noqa: PLC0415
        AnalyzeCapSkip,
        run_analyze_subprocess,
    )

    p = tmp_path / "tiny.3mf"
    _write_tiny_3mf(p)

    with pytest.raises(AnalyzeCapSkip, match="3MF geometry"):
        await run_analyze_subprocess(
            p,
            source_hash="e" * 64,
            timeout_s=60,
            mem_limit_mb=4096,
            max_3mf_xml_mb=0,
        )


# ---------------------------------------------------------------------------
# Timeout path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_analyze_subprocess_timeout_does_not_hang(tmp_path: Path) -> None:
    """timeout_s=0 → the child cannot finish bootstrapping in time → AnalyzeTimeout.

    Spawning a fresh interpreter always takes non-zero wall-clock time, so a
    zero-second timeout deterministically exercises the kill path. The await
    completing at all (rather than the test hanging) proves the parent event
    loop is never blocked on a stuck child.
    """
    from app.worker.analyze_subprocess import (  # noqa: PLC0415
        AnalyzeTimeout,
        run_analyze_subprocess,
    )

    p = tmp_path / "box.stl"
    _write_box_stl(p)

    with pytest.raises(AnalyzeTimeout, match="timed out"):
        await run_analyze_subprocess(
            p,
            source_hash="c" * 64,
            timeout_s=0,
            mem_limit_mb=4096,
            max_triangles=None,
        )
