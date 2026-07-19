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
