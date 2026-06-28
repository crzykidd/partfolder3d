"""Headless mesh rendering for PartFolder 3D (Phase 4 — render spike).

Parses STL / OBJ / PLY / 3MF via **trimesh** and renders an offscreen PNG using
the first available backend:

  1. pyrender + EGL      — fast; needs Mesa EGL (``libGL``, ``libegl1``).
  2. pyrender + OSMesa   — software; needs ``libosmesa6`` ≥ Mesa 21
                           (``OSMesaCreateContextAttribs`` required).
  3. VTK offscreen       — Mesa software rasterizer built into the VTK wheel.
                           Always works on a CPU-only host; no X11 or EGL needed.

Override auto-detection with the ``RENDER_BACKEND`` environment variable
(``"egl"``, ``"osmesa"``, ``"vtk"``, or ``"auto"``).

Configurable resolution via ``RENDER_RESOLUTION`` (default: ``512``).

A failed render raises ``RenderError`` — the caller (arq task) catches this and
marks the Job row failed without crashing the worker or blocking item creation.

Local dev verification
----------------------
- trimesh parsing: verified OK (STL/OBJ/PLY/3MF).
- VTK offscreen: verified OK on this host (CPU-only, no GPU/X11).
- pyrender+OSMesa: NOT verified locally (system OSMesa too old for
  ``OSMesaCreateContextAttribs``); expected to work in Docker (Debian bookworm Mesa).
- pyrender+EGL: NOT verified locally; expected to work in Docker with EGL libraries.
- Headless GL in general: may need confirmation in the Docker image / CI.
"""

from __future__ import annotations

import logging
import os
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import trimesh as _trimesh

log = logging.getLogger(__name__)

# Recognised mesh file extensions
MESH_EXTENSIONS = frozenset({".stl", ".obj", ".ply", ".3mf"})

RenderBackend = Literal["egl", "osmesa", "vtk", "none"]
_DETECTED_BACKEND: RenderBackend | None = None


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------


def _try_egl() -> bool:
    """Return True if pyrender can use EGL."""
    import sys  # noqa: PLC0415

    orig = os.environ.get("PYOPENGL_PLATFORM")
    try:
        os.environ["PYOPENGL_PLATFORM"] = "egl"
        import pyrender  # noqa: PLC0415, F401
        from OpenGL import EGL as _egl  # type: ignore[import]  # noqa: PLC0415

        # Probe for the eglGetDisplay symbol; assigning suppresses B018
        _egl_probe = _egl.eglGetDisplay
        del _egl_probe
        return True
    except Exception:
        # Restore platform so we don't leave a bad value
        if orig is None:
            os.environ.pop("PYOPENGL_PLATFORM", None)
        else:
            os.environ["PYOPENGL_PLATFORM"] = orig
        # Clear the OpenGL module cache so that _try_osmesa() can re-initialise
        # the OpenGL platform as "osmesa" rather than inheriting the failed "egl"
        # platform singleton (which would cause AttributeError on osmesa attributes).
        for _mod in list(sys.modules.keys()):
            if _mod.startswith("OpenGL"):
                del sys.modules[_mod]
        return False


def _try_osmesa() -> bool:
    """Return True if pyrender can use OSMesa (needs OSMesaCreateContextAttribs).

    We deliberately avoid ``import pyrender`` here because a failed ``_try_egl()``
    call earlier in the detection chain may have imported OpenGL with an EGL
    platform, leaving the global platform state in an inconsistent state.
    Checking importability via ``importlib.util.find_spec`` and doing the
    ``OpenGL.osmesa`` probe with ``PYOPENGL_PLATFORM=osmesa`` is sufficient to
    confirm the path is available without corrupting the state further.
    """
    import importlib.util  # noqa: PLC0415

    orig = os.environ.get("PYOPENGL_PLATFORM")
    try:
        # Confirm pyrender is installed without importing it (avoids platform lock-in)
        if importlib.util.find_spec("pyrender") is None:
            return False
        os.environ["PYOPENGL_PLATFORM"] = "osmesa"
        from OpenGL.osmesa import (
            OSMesaCreateContextAttribs,  # type: ignore[import]  # noqa: PLC0415, F401
        )

        return True
    except Exception:
        if orig is None:
            os.environ.pop("PYOPENGL_PLATFORM", None)
        else:
            os.environ["PYOPENGL_PLATFORM"] = orig
        return False


def _try_vtk() -> bool:
    """Return True if VTK offscreen rendering actually works on this host.

    The PyPI VTK wheel ships without EGL or OSMesa support; it falls back to
    the X11 GL path even when ``SetOffScreenRendering(True)`` is called.  On a
    headless host (no DISPLAY, no EGL) that path calls ``Abort()``, sending
    SIGABRT to the process — uncatchable by normal Python exception handling.

    We probe in a subprocess so a crash is contained; returncode 0 means
    VTK offscreen is confirmed usable.
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
    if forced not in ("auto", ""):
        log.info("render_mesh: using forced backend %r", forced)
        return forced  # type: ignore[return-value]

    if _try_egl():
        return "egl"
    if _try_osmesa():
        return "osmesa"
    if _try_vtk():
        return "vtk"
    return "none"


def get_backend() -> RenderBackend:
    """Return (and cache) the best available render backend."""
    global _DETECTED_BACKEND
    if _DETECTED_BACKEND is None:
        _DETECTED_BACKEND = _detect_backend()
        log.info("render_mesh: detected backend = %s", _DETECTED_BACKEND)
    return _DETECTED_BACKEND


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class RenderError(Exception):
    """Raised when rendering fails.  Non-fatal — callers mark the Job failed."""


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
# Renderer: pyrender (EGL or OSMesa)
# ---------------------------------------------------------------------------


def _render_pyrender(
    mesh: _trimesh.Trimesh,
    resolution: int,
    backend: str,
) -> bytes:
    """Render via pyrender (EGL or OSMesa; the PYOPENGL_PLATFORM env var must be set)."""
    import numpy as np  # noqa: PLC0415
    import pyrender  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    os.environ["PYOPENGL_PLATFORM"] = backend  # "egl" or "osmesa"

    scene = pyrender.Scene(bg_color=[0.15, 0.15, 0.18, 1.0])
    prmesh = pyrender.Mesh.from_trimesh(mesh, smooth=True)
    scene.add(prmesh)

    bounds = mesh.bounds
    center = (bounds[0] + bounds[1]) / 2.0
    extent = float(np.linalg.norm(bounds[1] - bounds[0]))
    d = extent * 1.5

    cam_pos = center + np.array([d, -d * 0.8, d * 0.6])
    forward = center - cam_pos
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)

    cam_pose = np.eye(4)
    cam_pose[:3, 0] = right
    cam_pose[:3, 1] = up
    cam_pose[:3, 2] = -forward
    cam_pose[:3, 3] = cam_pos

    camera = pyrender.PerspectiveCamera(yfov=np.pi / 3.5, aspectRatio=1.0)
    scene.add(camera, pose=cam_pose)
    scene.add(
        pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=2.0),
        pose=cam_pose,
    )

    r = pyrender.OffscreenRenderer(resolution, resolution)
    try:
        color, _ = r.render(scene)
    finally:
        r.delete()

    img = Image.fromarray(color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_mesh_file(path: Path, resolution: int = 512) -> bytes:
    """Render a single mesh file to PNG bytes.

    Args:
        path:       Absolute path to a mesh file (.stl / .obj / .ply / .3mf).
        resolution: Output image resolution in pixels (square).

    Returns:
        PNG image as raw bytes.

    Raises:
        RenderError: Parsing or rendering failed.  The caller is responsible for
                     logging this and marking the Job row failed.
    """
    suffix = path.suffix.lower()
    if suffix not in MESH_EXTENSIONS:
        raise RenderError(f"Unsupported file type {path.suffix!r} — skipping (not a mesh)")

    backend = get_backend()
    if backend == "none":
        raise RenderError(
            "No rendering backend available "
            "(need pyrender+EGL, pyrender+OSMesa, or vtk — see requirements.txt / Dockerfile)"
        )

    try:
        mesh = _load_as_trimesh(path)
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(f"trimesh failed to parse {path.name}: {exc}") from exc

    if not len(mesh.vertices) or not len(mesh.faces):
        raise RenderError(f"Empty mesh in {path.name} — skipping render")

    try:
        if backend == "vtk":
            return _render_vtk(mesh, resolution)
        elif backend in ("egl", "osmesa"):
            return _render_pyrender(mesh, resolution, backend)
        else:
            raise RenderError(f"Unknown backend {backend!r}")
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(f"Rendering failed ({backend}): {exc}") from exc
