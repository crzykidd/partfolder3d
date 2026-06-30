"""Subprocess-based mesh render runner with wall-clock timeout.

Runs ``render_mesh_file`` in a fresh spawned child process so the async event
loop is never blocked and the child can be killed when it exceeds the timeout.

Why ``spawn`` (not ``fork``)?  GL/OSMesa/VTK initialise global state at import
time; forking after that initialisation can deadlock in multi-threaded contexts.
A fresh ``spawn`` process always starts with a clean interpreter.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


class RenderTimeout(Exception):
    """Raised when the render child process exceeds RENDER_TIMEOUT_S."""


# ---------------------------------------------------------------------------
# Child-process entry point
# ---------------------------------------------------------------------------


def _render_worker(
    path_str: str,
    resolution: int,
    out_file: str,
    err_file: str,
) -> None:
    """Top-level entry point executed in the spawned child process.

    Writes PNG bytes to *out_file* on success; writes an error string to
    *err_file* on failure.  Both paths are pre-created temporaries.
    Imports are deferred so the fresh interpreter loads them clean.
    """
    from app.worker.render_mesh import RenderError, render_mesh_file  # noqa: PLC0415

    try:
        png = render_mesh_file(Path(path_str), resolution=resolution)
        Path(out_file).write_bytes(png)
    except RenderError as exc:
        Path(err_file).write_text(str(exc))
    except Exception as exc:  # noqa: BLE001
        Path(err_file).write_text(f"unexpected: {exc}")


# ---------------------------------------------------------------------------
# Async parent-side runner
# ---------------------------------------------------------------------------


async def run_render_subprocess(
    path: Path,
    resolution: int,
    timeout_s: int,
) -> bytes:
    """Run ``render_mesh_file`` in a spawned child; return PNG bytes.

    The child process is started with ``multiprocessing.get_context("spawn")``
    so it never inherits GL / OpenGL / Mesa state from the parent.  The parent
    awaits child completion via ``asyncio.to_thread`` so the event loop is free
    to service other coroutines while the child renders.

    Args:
        path:       Absolute path to the mesh file.
        resolution: Square thumbnail resolution in pixels.
        timeout_s:  Wall-clock kill timeout in seconds.

    Returns:
        PNG image as raw bytes.

    Raises:
        RenderTimeout:  Child exceeded the wall-clock timeout and was killed.
        RenderError:    Child reported a render failure.
    """
    from app.worker.render_mesh import RenderError  # noqa: PLC0415

    ctx = multiprocessing.get_context("spawn")

    # Pre-create temp files (the child writes to them).
    out_fd, out_path = tempfile.mkstemp(suffix=".png")
    os.close(out_fd)
    err_fd, err_path = tempfile.mkstemp(suffix=".err")
    os.close(err_fd)

    proc = ctx.Process(
        target=_render_worker,
        args=(str(path), resolution, out_path, err_path),
        daemon=True,
    )

    try:
        proc.start()

        # Wait for the child without blocking the event loop.
        await asyncio.to_thread(proc.join, timeout_s)

        if proc.is_alive():
            log.warning(
                "run_render_subprocess: timeout (%ds) for %s — terminating child pid=%s",
                timeout_s,
                path.name,
                proc.pid,
            )
            proc.terminate()
            await asyncio.to_thread(proc.join, 5)
            if proc.is_alive():
                proc.kill()
                await asyncio.to_thread(proc.join, 2)
            raise RenderTimeout(f"render timed out after {timeout_s}s for {path.name}")

        # Child exited — read results.
        err_text = Path(err_path).read_text().strip()
        if err_text:
            raise RenderError(err_text)

        out_bytes = Path(out_path).read_bytes()
        if not out_bytes:
            raise RenderError(f"render produced empty output for {path.name}")

        return out_bytes

    finally:
        for p in (out_path, err_path):
            try:
                Path(p).unlink()
            except OSError:
                pass
        # Belt-and-suspenders: kill if still alive (e.g. RenderError raised above
        # after a non-timeout exit, but before we hit the finally).
        if proc.is_alive():
            proc.kill()
