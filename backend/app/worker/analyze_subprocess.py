"""Subprocess-based mesh analysis runner with wall-clock timeout AND memory bound.

Runs ``mesh_analysis.analyze_file`` in a fresh spawned child process so a
pathological mesh (a huge allocation, a degenerate geometry that hangs a
trimesh routine, or an outright crash) can never take down the whole arq
worker — only the one file's analysis fails (issue #37 fix #2).

Why ``spawn`` (not ``fork``)?  A fresh interpreter avoids inheriting any
half-initialised numpy / trimesh / BLAS thread-pool state from the parent —
same rationale as ``render_subprocess.py``.

Why is a per-child ``RLIMIT_AS`` required on top of subprocess isolation?
The worker container has ONE cgroup memory cap shared by every process inside
it.  If the analyze work only ran in a bare subprocess, an over-large
allocation in the CHILD could still push total container RSS over the cgroup
limit — and the kernel OOM-killer picks its victim by heuristic, which is
**not guaranteed to be the child**; it can just as easily kill the PARENT
(the whole worker), taking every other in-flight job down with it.  Setting
``RLIMIT_AS`` in the child — BEFORE importing trimesh/numpy — bounds that
process's own virtual address space, so an over-limit allocation raises a
catchable ``MemoryError`` inside the child (or the child alone is killed by
the kernel) — either way the parent worker survives.
"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# RLIMIT_AS floor — never bind the child under this even if a caller passes an
# absurdly low mem_limit_mb.  Importing numpy/trimesh/lxml alone needs some
# headroom; setting the cap too low would make every analysis fail immediately.
_MIN_MEM_LIMIT_MB = 1024


class AnalyzeTimeout(Exception):
    """Raised when the analyze child process exceeds ANALYZE_TIMEOUT_S."""


class AnalyzeCapSkip(Exception):
    """Raised when the child signals a cap-skip (triangle count over the cap).

    Not treated as an error — the caller stores a low-confidence stub result
    (see ``app.worker.tasks.analysis``) rather than counting it as a failure.
    """


class AnalyzeError(Exception):
    """Raised when the child fails (crash, OOM, unexpected exception)."""


# ---------------------------------------------------------------------------
# Child-process entry point
# ---------------------------------------------------------------------------


def _analyze_worker(
    path_str: str,
    density_g_cm3: float,
    infill_pct: float,
    source_hash: str | None,
    max_triangles: int | None,
    max_3mf_xml_mb: int | None,
    mem_limit_mb: int,
    out_file: str,
    err_file: str,
) -> None:
    """Top-level entry point executed in the spawned child process.

    Writes the FileAnalysis dict as JSON to *out_file* on success (it is
    already JSON-serialisable — this is exactly what gets stored in the
    File.object_analysis JSONB column).  Writes an error string to *err_file*
    on failure.  Both paths are pre-created temporaries.

    Sets numeric-thread env caps (mirrors ``startup()`` in ``worker.py``) AND
    ``RLIMIT_AS`` BEFORE importing trimesh/numpy/lxml, so the memory bound
    governs their allocations too — see the module docstring for why this is
    required on top of subprocess isolation alone.

    Cap-skip (too many triangles) is signalled with the ``__CAP_SKIP__:``
    prefix so the parent can raise ``AnalyzeCapSkip`` (not treated as an
    error).
    """
    from app.config import settings  # noqa: PLC0415

    thread_count = str(settings.RENDER_CPU_THREADS)
    for _var in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "LP_NUM_THREADS",
    ):
        os.environ[_var] = thread_count

    import resource  # noqa: PLC0415

    limit_bytes = max(mem_limit_mb, _MIN_MEM_LIMIT_MB) * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    except (ValueError, OSError) as exc:
        # Some sandboxed/containerized environments refuse to lower RLIMIT_AS
        # further than an existing hard limit. Log and continue — subprocess
        # isolation + the wall-clock timeout still bound the blast radius.
        log.warning(
            "_analyze_worker: could not set RLIMIT_AS to %d bytes: %s", limit_bytes, exc
        )

    from app.worker.mesh_analysis import MeshTooLargeError, analyze_file  # noqa: PLC0415

    try:
        result = analyze_file(
            Path(path_str),
            density_g_cm3=density_g_cm3,
            infill_pct=infill_pct,
            source_hash=source_hash,
            max_triangles=max_triangles,
            max_3mf_xml_mb=max_3mf_xml_mb,
        )
        Path(out_file).write_text(json.dumps(result))
    except MeshTooLargeError as exc:
        Path(err_file).write_text(f"__CAP_SKIP__: {exc}")
    except MemoryError as exc:
        Path(err_file).write_text(f"out of memory (RLIMIT_AS bound): {exc}")
    except Exception as exc:  # noqa: BLE001
        Path(err_file).write_text(f"unexpected: {exc}")


# ---------------------------------------------------------------------------
# Async parent-side runner
# ---------------------------------------------------------------------------


async def run_analyze_subprocess(
    path: Path,
    *,
    density_g_cm3: float = 1.24,
    infill_pct: float = 15.0,
    source_hash: str | None = None,
    timeout_s: int,
    mem_limit_mb: int,
    max_triangles: int | None = None,
    max_3mf_xml_mb: int | None = None,
) -> dict[str, Any]:
    """Run ``analyze_file`` in a spawned child; return the FileAnalysis dict.

    The child process is started with ``multiprocessing.get_context("spawn")``
    so it always begins with a clean interpreter (no inherited numpy/BLAS
    thread-pool state).  The parent awaits child completion via
    ``asyncio.to_thread`` so the event loop stays free to service other
    coroutines while the child analyzes.

    Args:
        path:           Absolute path to the mesh file.
        density_g_cm3:  Filament density (g/cm³) for the grams estimate.
        infill_pct:     Infill percentage (0-100) for the grams estimate.
        source_hash:    sha256 of the file bytes; computed in the child if None.
        timeout_s:      Wall-clock kill timeout in seconds.
        mem_limit_mb:   Per-child RLIMIT_AS bound in MB (floored to 1024).
        max_triangles:  Triangle-count cap; None = no cap.
        max_3mf_xml_mb: 3MF geometry-XML pre-load size cap in MB (issue #37
                        follow-up); None = no cap. No-op for non-3MF files.

    Returns:
        FileAnalysis dict (same shape as ``mesh_analysis.analyze_file``).

    Raises:
        AnalyzeTimeout:  Child exceeded the wall-clock timeout and was killed.
        AnalyzeCapSkip:  Child reported a cap-skip (too many triangles).
        AnalyzeError:    Child reported an analysis failure (crash / OOM).
    """
    ctx = multiprocessing.get_context("spawn")

    # Pre-create temp files (the child writes to them).
    out_fd, out_path = tempfile.mkstemp(suffix=".json")
    os.close(out_fd)
    err_fd, err_path = tempfile.mkstemp(suffix=".err")
    os.close(err_fd)

    proc = ctx.Process(
        target=_analyze_worker,
        args=(
            str(path),
            density_g_cm3,
            infill_pct,
            source_hash,
            max_triangles,
            max_3mf_xml_mb,
            mem_limit_mb,
            out_path,
            err_path,
        ),
        daemon=True,
    )

    try:
        proc.start()

        # Wait for the child without blocking the event loop.
        await asyncio.to_thread(proc.join, timeout_s)

        if proc.is_alive():
            log.warning(
                "run_analyze_subprocess: timeout (%ds) for %s — terminating child pid=%s",
                timeout_s,
                path.name,
                proc.pid,
            )
            proc.terminate()
            await asyncio.to_thread(proc.join, 5)
            if proc.is_alive():
                proc.kill()
                await asyncio.to_thread(proc.join, 2)
            raise AnalyzeTimeout(f"analyze timed out after {timeout_s}s for {path.name}")

        # Child exited — read results.
        err_text = Path(err_path).read_text().strip()
        if err_text.startswith("__CAP_SKIP__:"):
            raise AnalyzeCapSkip(err_text[len("__CAP_SKIP__:"):].strip())
        if err_text:
            raise AnalyzeError(err_text)

        out_text = Path(out_path).read_text()
        if not out_text:
            raise AnalyzeError(f"analyze produced empty output for {path.name}")

        result: dict[str, Any] = json.loads(out_text)
        return result

    finally:
        for p in (out_path, err_path):
            try:
                Path(p).unlink()
            except OSError:
                pass
        # Belt-and-suspenders: kill if still alive (e.g. AnalyzeError raised
        # above after a non-timeout exit, but before we hit the finally).
        if proc.is_alive():
            proc.kill()
