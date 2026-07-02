"""Headless mesh rendering for PartFolder 3D.

Renders STL / OBJ / PLY files to an offscreen PNG using **VTK's built-in Mesa
software rasterizer** (no GPU, no EGL, no OSMesa system packages required).

3MF files are NOT rendered here — they have embedded slicer thumbnails which
are extracted by the ``threemf`` module instead.

Configurable resolution via ``RENDER_RESOLUTION`` (default: ``512``).

A failed render raises ``RenderError`` — the caller (arq task) catches this and
marks the Job row failed without crashing the worker or blocking item creation.

``RenderCapSkip`` is raised (not an error) when a file exceeds the configured
size or triangle cap.  Callers should log and silently skip — no Job failure.

Local dev verification
----------------------
- VTK offscreen: verified OK on this host (CPU-only, no GPU/X11).
- Headless GL in general: confirmed in Docker (VTK bundles Mesa).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import trimesh as _trimesh

log = logging.getLogger(__name__)

# Recognised mesh file extensions that the server will render.
# .3mf is intentionally excluded — slicer thumbnails are preferred.
MESH_EXTENSIONS = frozenset({".stl", ".obj", ".ply"})

RenderBackend = Literal["vtk", "none"]
_DETECTED_BACKEND: RenderBackend | None = None


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class RenderError(Exception):
    """Raised when rendering fails.  Non-fatal — callers mark the Job failed."""


class RenderCapSkip(Exception):
    """Raised when a file exceeds size or triangle caps.

    This is NOT an error — the caller should skip silently (log + no Image row).
    """


# ---------------------------------------------------------------------------
# Backend detection (VTK-only)
# ---------------------------------------------------------------------------


def _try_vtk() -> bool:
    """Return True if VTK offscreen rendering works on this host.

    Probes in a subprocess so a crash (SIGABRT on headless X11) is contained.
    """
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    try:
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import vtk; rw=vtk.vtkRenderWindow(); "
                    "rw.SetOffScreenRendering(True); rw.SetSize(4,4); "
                    "rw.Render(); print('ok')"
                ),
            ],
            capture_output=True,
            timeout=10,
        )
        return probe.returncode == 0 and b"ok" in probe.stdout
    except Exception:
        return False


def _detect_backend() -> RenderBackend:
    forced = os.environ.get("RENDER_BACKEND", "auto").lower().strip()
    if forced == "vtk":
        return "vtk"
    if forced not in ("auto", ""):
        log.warning("render_mesh: unknown RENDER_BACKEND=%r; trying vtk", forced)

    if _try_vtk():
        return "vtk"
    return "none"


def get_backend() -> RenderBackend:
    """Return (and cache) the available render backend."""
    global _DETECTED_BACKEND
    if _DETECTED_BACKEND is None:
        _DETECTED_BACKEND = _detect_backend()
        log.info("render_mesh: detected backend = %s", _DETECTED_BACKEND)
    return _DETECTED_BACKEND


# ---------------------------------------------------------------------------
# Mesh loading
# ---------------------------------------------------------------------------


def _load_as_trimesh(path: Path) -> _trimesh.Trimesh:
    """Load a mesh file; return a single ``trimesh.Trimesh`` (merges multi-body scenes)."""
    import trimesh  # noqa: PLC0415
    import trimesh.util  # noqa: PLC0415

    loaded = trimesh.load(str(path))
    if isinstance(loaded, trimesh.Scene):
        meshes = list(loaded.geometry.values())
        if not meshes:
            raise RenderError(f"Scene contains no meshes: {path.name}")
        if len(meshes) == 1:
            return meshes[0]
        return trimesh.util.concatenate(meshes)
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    raise RenderError(f"Unexpected trimesh result type {type(loaded).__name__} for {path.name}")


# ---------------------------------------------------------------------------
# Renderer: VTK
# ---------------------------------------------------------------------------


def _render_vtk(mesh: _trimesh.Trimesh, resolution: int) -> bytes:
    """Render via VTK's built-in Mesa software offscreen rasterizer."""
    import numpy as np  # noqa: PLC0415
    import vtk  # noqa: PLC0415

    # -- Build vtkPolyData from trimesh
    points = vtk.vtkPoints()
    for v in mesh.vertices:
        points.InsertNextPoint(float(v[0]), float(v[1]), float(v[2]))

    cells = vtk.vtkCellArray()
    for f in mesh.faces:
        tri = vtk.vtkTriangle()
        tri.GetPointIds().SetId(0, int(f[0]))
        tri.GetPointIds().SetId(1, int(f[1]))
        tri.GetPointIds().SetId(2, int(f[2]))
        cells.InsertNextCell(tri)

    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(cells)

    # Smooth normals for shading
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(polydata)
    normals.ComputePointNormalsOn()
    normals.ConsistencyOn()
    normals.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.75, 0.78, 0.85)
    actor.GetProperty().SetAmbient(0.2)
    actor.GetProperty().SetDiffuse(0.7)
    actor.GetProperty().SetSpecular(0.3)
    actor.GetProperty().SetSpecularPower(20.0)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.SetBackground(0.15, 0.15, 0.18)

    # Camera: isometric-ish view from top-right-front
    renderer.ResetCamera()
    camera = renderer.GetActiveCamera()
    bounds = mesh.bounds
    center = (bounds[0] + bounds[1]) / 2.0
    extent = float(np.linalg.norm(bounds[1] - bounds[0]))
    camera.SetFocalPoint(float(center[0]), float(center[1]), float(center[2]))
    d = extent * 1.5
    camera.SetPosition(
        float(center[0] + d),
        float(center[1] - d * 0.8),
        float(center[2] + d * 0.6),
    )
    camera.SetViewUp(0.0, 0.0, 1.0)
    renderer.ResetCameraClippingRange()

    # Two-light setup: key + fill
    key = vtk.vtkLight()
    key.SetLightTypeToCameraLight()
    key.SetPosition(1.0, -1.0, 2.0)
    key.SetIntensity(0.9)
    renderer.AddLight(key)

    fill = vtk.vtkLight()
    fill.SetLightTypeToCameraLight()
    fill.SetPosition(-1.0, 0.5, 0.5)
    fill.SetIntensity(0.4)
    renderer.AddLight(fill)

    rw = vtk.vtkRenderWindow()
    rw.AddRenderer(renderer)
    rw.SetOffScreenRendering(True)
    rw.SetSize(resolution, resolution)
    rw.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(rw)
    w2i.Update()

    writer = vtk.vtkPNGWriter()
    writer.WriteToMemoryOn()
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()

    return bytes(writer.GetResult())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_mesh_file(
    path: Path,
    resolution: int = 512,
    max_triangles: int = 1_000_000,
) -> bytes:
    """Render a single mesh file to PNG bytes.

    Only STL / OBJ / PLY are accepted.  3MF is explicitly excluded — use
    the ``threemf`` module to extract the embedded slicer thumbnail instead.

    Args:
        path:          Absolute path to a mesh file (.stl / .obj / .ply).
        resolution:    Output image resolution in pixels (square).
        max_triangles: Triangle count cap.  Meshes over this limit raise
                       ``RenderCapSkip`` (not a failure — silently skipped).

    Returns:
        PNG image as raw bytes.

    Raises:
        RenderError:   Parsing or rendering failed.
        RenderCapSkip: File exceeds the triangle cap.
    """
    suffix = path.suffix.lower()
    if suffix not in MESH_EXTENSIONS:
        raise RenderError(
            f"Unsupported file type {path.suffix!r} — only STL/OBJ/PLY are rendered "
            "(3MF uses embedded slicer thumbnails instead)"
        )

    backend = get_backend()
    if backend == "none":
        raise RenderError(
            "No rendering backend available (need vtk — see requirements.txt / Dockerfile)"
        )

    try:
        mesh = _load_as_trimesh(path)
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(f"trimesh failed to parse {path.name}: {exc}") from exc

    if not len(mesh.vertices) or not len(mesh.faces):
        raise RenderError(f"Empty mesh in {path.name} — skipping render")

    # Triangle cap: checked after load (no pre-load triangle count API for all formats)
    if len(mesh.faces) > max_triangles:
        raise RenderCapSkip(
            f"{path.name} has {len(mesh.faces):,} triangles "
            f"(cap {max_triangles:,}) — skipping render"
        )

    try:
        return _render_vtk(mesh, resolution)
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(f"Rendering failed (vtk): {exc}") from exc
