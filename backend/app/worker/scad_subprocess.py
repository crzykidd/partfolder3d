"""Subprocess-isolated OpenSCAD compile (.scad -> .stl) with wall-clock timeout.

``.scad`` is a Turing-complete language — it can loop, allocate large data
structures, and read other files via ``import()``/``include()``/``use()`` — so a
compile MUST run with the same rigor as ``render_subprocess.py`` /
``analyze_subprocess.py``: an isolated child process, a wall-clock kill
timeout, memory/CPU rlimits, and a scratch workdir.

Why this module looks different from render/analyze's ``multiprocessing.get_
context("spawn")`` dance: render and analyze run heavy *Python* code (VTK /
trimesh / numpy) directly in-process in the child, so they need a fresh
interpreter (spawn, not fork) to avoid inheriting half-initialised GL/BLAS
state. Here the actual work is an *external binary* (``openscad``) — it is
already its own OS process the moment it is exec'd, so a plain
``asyncio.create_subprocess_exec`` child gives the same isolation (its own
address space, its own rlimits via ``preexec_fn``, killable independent of the
parent) without any multiprocessing machinery.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# RLIMIT_AS / RLIMIT_CPU floors — never bind the child under these even if a
# caller passes an absurdly low setting. OpenSCAD's CGAL/GMP/MPFR geometry
# kernel needs some headroom just to start up.
_MIN_MEM_LIMIT_MB = 512
_MIN_CPU_LIMIT_S = 5


class ScadTimeout(Exception):
    """Raised when the compile child exceeds SCAD_RENDER_TIMEOUT_S."""


class ScadCompileError(Exception):
    """Raised when the compile fails (missing binary, bad geometry, non-zero exit, OOM)."""


def openscad_available() -> bool:
    """True if the ``openscad`` binary is on PATH.

    Used both to fail fast with a clear error and to let tests/CI skip the
    "real binary" integration test on a host/CI runner without OpenSCAD
    installed (the live worker image gets it via the Dockerfile deps stage;
    older/un-rebuilt worker images won't have it yet).
    """
    return shutil.which("openscad") is not None


def _rlimit_preexec(mem_limit_mb: int, cpu_limit_s: int):  # type: ignore[no-untyped-def]
    """Build a ``preexec_fn`` that sets RLIMIT_AS + RLIMIT_CPU in the child.

    Runs in the forked child AFTER ``fork()`` but BEFORE ``exec()``, so the
    limits bind to the ``openscad`` process itself. Best-effort: some
    sandboxed/containerized environments refuse to lower a limit past an
    existing hard limit — swallow and continue (the wall-clock timeout below
    still bounds the blast radius either way).
    """

    def _set_limits() -> None:
        import resource  # noqa: PLC0415

        mem_bytes = max(mem_limit_mb, _MIN_MEM_LIMIT_MB) * 1024 * 1024
        cpu_s = max(cpu_limit_s, _MIN_CPU_LIMIT_S)
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        except (ValueError, OSError):
            pass

    return _set_limits


async def run_scad_compile_subprocess(
    scad_path: Path,
    out_stl_path: Path,
    *,
    workdir: Path,
    timeout_s: int,
    mem_limit_mb: int,
    cpu_limit_s: int,
) -> None:
    """Compile *scad_path* to *out_stl_path* in an isolated ``openscad`` child.

    Args:
        scad_path:    Absolute path to the ``.scad`` file to compile, INSIDE
                      *workdir* (so any relative ``include``/``use`` of a
                      sibling file uploaded alongside it resolves; anything
                      else — a missing library, an absolute-path ``import()``
                      outside the sandbox — fails the compile, which is the
                      intended "compile only what was uploaded together"
                      behaviour, issue #46).
        out_stl_path: Where the child should write the STL (inside *workdir*).
        workdir:      Scratch directory the child runs in (``cwd``). Caller
                      creates and removes it.
        timeout_s:    Wall-clock kill timeout in seconds.
        mem_limit_mb: RLIMIT_AS bound in MB (floored to 512).
        cpu_limit_s:  RLIMIT_CPU bound in seconds (floored to 5).

    Raises:
        ScadTimeout:      Child exceeded the wall-clock timeout and was killed.
        ScadCompileError: Missing binary, non-zero exit, or no/empty output.
    """
    if not openscad_available():
        raise ScadCompileError("openscad binary not found on PATH")

    proc = await asyncio.create_subprocess_exec(
        "openscad",
        "-o",
        str(out_stl_path),
        str(scad_path),
        cwd=str(workdir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=_rlimit_preexec(mem_limit_mb, cpu_limit_s),
        start_new_session=True,  # own process group -> killpg reaches any child procs
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        log.warning(
            "run_scad_compile_subprocess: timeout (%ds) for %s — terminating child pid=%s",
            timeout_s, scad_path.name, proc.pid,
        )
        await _kill_process_group(proc)
        raise ScadTimeout(
            f"openscad compile timed out after {timeout_s}s for {scad_path.name}"
        ) from None

    if proc.returncode != 0:
        err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
        raise ScadCompileError(
            f"openscad exited {proc.returncode} for {scad_path.name}: "
            f"{err_text[-2000:] if err_text else '(no stderr)'}"
        )

    if not out_stl_path.exists() or out_stl_path.stat().st_size == 0:
        err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
        raise ScadCompileError(
            f"openscad produced no/empty output for {scad_path.name}"
            + (f": {err_text[-500:]}" if err_text else "")
        )


async def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    """SIGTERM the child's process group, escalate to SIGKILL if it won't die."""
    import contextlib
    import os
    import signal

    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=2)
