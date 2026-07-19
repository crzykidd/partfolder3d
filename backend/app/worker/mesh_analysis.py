"""Per-object mesh analysis: colors + estimated filament grams.

Statically analyzes STL and 3MF files to produce per-object statistics
without requiring any print log or slicer:

  - color_count / colors  — distinct colors per object (see notes below)
  - est_grams             — volume × density × infill_factor (ROUGH ESTIMATE)
  - volume_cm3 / dims_mm  — geometry measurements
  - watertight / low_confidence — mesh quality flags

Color sources:
  STL    → always 1 (no color information in file format).
  3MF standard  → lxml-parsed basematerials + colorgroup elements from
                   3D/3dmodel.model inside the ZIP.  Object-level default
                   material AND per-triangle p1/p2/p3 references are resolved.
                   Raw hex strings stored (no name-matching).
  3MF vendor paint (best-effort, Bambu/Orca)
            → per-triangle ``paint_color`` or ``mmu_segmentation`` attributes.
              Distinct non-zero values are counted as a proxy for color count.
              Hex values are NOT decoded (would need slicer context for filament
              lookup); these are flagged ``has_vendor_paint=True`` in logs.
              If standard material colors are already found, vendor paint is
              ignored (standard wins).
  OBJ / PLY → treated as 1 object, 1 color.

Grams estimate (store est_method='volume' for future slicer upgrade):
  grams = volume_cm3 × density_g_cm3 × (infill_pct / 100.0)

  Defaults: density=1.24 g/cm³ (PLA), infill=15 %.
  WARNING: this can be 2–5× off.  It ignores wall thickness, support
  material, and actual slicer strategies.  The UI MUST label it an estimate.
  A future ``est_method='sliced'`` path can replace the value with no schema
  change.

Non-watertight handling (per object):
  1. mesh.is_watertight → if True, use mesh.volume directly.
  2. fill_holes() light repair → recheck.
  3. Still non-watertight → convex hull volume, set low_confidence=True.
  4. If even hull fails → volume=None, est_grams=None, low_confidence=True.
  Never crash; best-effort per object.

Usage:
  analysis = analyze_file(path, density_g_cm3=1.24, infill_pct=15.0)
  # analysis = {
  #   'analyzed_at': '<ISO datetime>',
  #   'source_hash': '<sha256>',
  #   'objects': [ObjectAnalysis, ...],
  #   'total_objects': N,
  #   'total_colors': N,
  #   'total_est_grams': N.NN,
  # }
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Extensions we know how to analyze
MESH_ANALYSIS_EXTENSIONS = frozenset({".stl", ".3mf", ".obj", ".ply"})


class MeshTooLargeError(Exception):
    """Raised when a mesh's triangle count exceeds the ``max_triangles`` cap.

    Not a load/parse failure — the caller (``analyze_subprocess``'s child entry
    point) converts this into a ``__CAP_SKIP__:`` signal so the parent raises
    ``AnalyzeCapSkip`` and stores a low-confidence stub result instead of
    treating it as an analysis error (issue #37 fix #4).
    """

# 3MF XML namespaces
_NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
_NS_MAT = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"


# ---------------------------------------------------------------------------
# Type aliases (dicts — avoid TypedDict deps for simpler import)
# ---------------------------------------------------------------------------

ObjectAnalysis = dict[str, Any]
FileAnalysis = dict[str, Any]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _safe_volume_cm3(mesh: Any) -> tuple[float | None, bool, bool]:
    """Return (volume_cm3, watertight, low_confidence) for a trimesh Trimesh.

    Steps:
    1. If mesh.is_watertight → abs(volume) / 1000 (mm³ → cm³).
    2. Try fill_holes() → recheck.
    3. Fallback convex hull → low_confidence=True.
    4. All else fails → None, low_confidence=True.
    """
    # Step 1: check watertight
    if getattr(mesh, "is_watertight", False):
        try:
            v = float(abs(mesh.volume)) / 1000.0
            return v, True, False
        except Exception:
            pass

    # Step 2: try fill_holes
    try:
        mesh.fill_holes()
    except Exception:
        pass

    if getattr(mesh, "is_watertight", False):
        try:
            v = float(abs(mesh.volume)) / 1000.0
            return v, True, False
        except Exception:
            pass

    # Step 3: convex hull fallback
    try:
        hull = mesh.convex_hull
        v = float(abs(hull.volume)) / 1000.0
        return v, False, True
    except Exception:
        pass

    return None, False, True


def _safe_dims_mm(mesh: Any) -> list[float] | None:
    """Return [x, y, z] bounding-box extents in mm, or None on error."""
    try:
        import numpy as np  # noqa: PLC0415

        bounds = mesh.bounds  # shape (2, 3)
        extents = np.array(bounds[1]) - np.array(bounds[0])
        return [  # noqa: FURB118
            round(float(extents[0]), 2),
            round(float(extents[1]), 2),
            round(float(extents[2]), 2),
        ]
    except Exception:
        return None


def _est_grams(volume_cm3: float | None, density: float, infill_pct: float) -> float | None:
    """Compute estimated grams; returns None when volume unknown."""
    if volume_cm3 is None:
        return None
    factor = max(0.01, min(1.0, infill_pct / 100.0))
    return round(volume_cm3 * density * factor, 3)


def _make_object_result(
    name: str,
    mesh: Any,
    colors: list[str],
    color_count: int,
    density: float,
    infill_pct: float,
) -> ObjectAnalysis:
    """Build a single ObjectAnalysis dict from a trimesh.Trimesh."""
    volume_cm3, watertight, low_confidence = _safe_volume_cm3(mesh)
    dims = _safe_dims_mm(mesh)
    grams = _est_grams(volume_cm3, density, infill_pct)
    return {
        "name": name,
        "color_count": max(1, color_count) if color_count else max(1, len(colors)),
        "colors": colors,
        "volume_cm3": round(volume_cm3, 6) if volume_cm3 is not None else None,
        "est_grams": grams,
        "est_method": "volume",
        "watertight": watertight,
        "low_confidence": low_confidence,
        "dims_mm": dims,
    }


# ---------------------------------------------------------------------------
# 3MF color parsing (lxml)
# ---------------------------------------------------------------------------


def _parse_3mf_colors(zip_bytes: bytes) -> dict[str, tuple[list[str], bool]]:
    """Parse 3D/3dmodel.model inside a 3MF ZIP for per-object colors.

    Returns: {object_id: ([hex_color, ...], has_vendor_paint)}

    Standard materials (basematerials, m:colorgroup) are parsed via lxml.
    Bambu/Orca vendor-paint (paint_color / mmu_segmentation on triangles)
    is detected on a best-effort basis: we count distinct non-zero paint_color
    values as a proxy for color count but do NOT decode the bitfield (requires
    slicer filament context).  When standard colors are found for an object,
    vendor paint is ignored.
    """
    try:
        from lxml import etree  # noqa: PLC0415
    except ImportError:
        log.warning("mesh_analysis: lxml not available; 3MF colors cannot be parsed")
        return {}

    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            model_path = next(
                (n for n in names if n.lower() == "3d/3dmodel.model"),
                None,
            )
            if model_path is None:
                log.debug("mesh_analysis: 3D/3dmodel.model not found in ZIP")
                return {}
            xml_data = zf.read(model_path)
    except Exception as exc:
        log.warning("mesh_analysis: could not read 3MF ZIP: %s", exc)
        return {}

    try:
        root = etree.fromstring(xml_data)  # type: ignore[attr-defined]
    except Exception as exc:
        log.warning("mesh_analysis: lxml parse error on 3dmodel.model: %s", exc)
        return {}

    resources = root.find(f"{{{_NS_3MF}}}resources")
    if resources is None:
        return {}

    # Build material group map: group_id → [hex_color, ...]
    mat_groups: dict[str, list[str]] = {}

    # Standard: basematerials
    for bm in resources.findall(f"{{{_NS_3MF}}}basematerials"):
        gid = bm.get("id", "")
        colors = [
            b.get("displaycolor", "").upper()
            for b in bm.findall(f"{{{_NS_3MF}}}base")
            if b.get("displaycolor")
        ]
        mat_groups[gid] = colors

    # Extension: m:colorgroup
    for cg in resources.findall(f"{{{_NS_MAT}}}colorgroup"):
        gid = cg.get("id", "")
        colors = [
            c.get("color", "").upper()
            for c in cg.findall(f"{{{_NS_MAT}}}color")
            if c.get("color")
        ]
        mat_groups[gid] = colors

    result: dict[str, tuple[list[str], bool]] = {}

    for obj in resources.findall(f"{{{_NS_3MF}}}object"):
        obj_id = obj.get("id", "")
        obj_pid = obj.get("pid", "")
        obj_pindex = obj.get("pindex", "0")

        collected_colors: set[str] = set()
        vendor_paint_values: set[str] = set()

        # Object-level default material
        if obj_pid and obj_pid in mat_groups:
            group = mat_groups[obj_pid]
            try:
                idx = int(obj_pindex)
            except ValueError:
                idx = 0
            if 0 <= idx < len(group) and group[idx]:
                collected_colors.add(group[idx])
            elif group:
                # pindex out of range or missing: use first
                collected_colors.add(group[0])

        # Parse triangles for per-face material refs
        mesh_elem = obj.find(f"{{{_NS_3MF}}}mesh")
        if mesh_elem is not None:
            triangles_elem = mesh_elem.find(f"{{{_NS_3MF}}}triangles")
            if triangles_elem is not None:
                for tri in triangles_elem:
                    # Standard 3MF: triangle-level material references
                    tri_pid = tri.get("pid", obj_pid)
                    if tri_pid and tri_pid in mat_groups:
                        group = mat_groups[tri_pid]
                        for attr in ("p1", "p2", "p3"):
                            pval = tri.get(attr, "")
                            if pval:
                                try:
                                    idx = int(pval)
                                except ValueError:
                                    continue
                                if 0 <= idx < len(group) and group[idx]:
                                    collected_colors.add(group[idx])

                    # Best-effort Bambu/Orca paint
                    pc = tri.get("paint_color", "").strip()
                    if pc and pc not in ("", "0", "0x0", "0x00", "0x"):
                        vendor_paint_values.add(pc)

                    mmu = tri.get("mmu_segmentation", "").strip()
                    if mmu:
                        # OrcaSlicer mmu_segmentation: base64-encoded per-face data
                        # We just flag its presence; can't decode without knowing
                        # how many extruders are configured
                        vendor_paint_values.add("__mmu__")

        # If standard colors found, ignore vendor paint for color list
        # (but still flag has_vendor_paint so caller knows)
        has_vendor_paint = bool(vendor_paint_values)

        if not collected_colors and has_vendor_paint:
            # No standard colors — use vendor paint count as proxy
            # distinct paint_color values (excluding MMU placeholder) + 1 base
            paint_hex_vals = {v for v in vendor_paint_values if not v.startswith("__")}
            if paint_hex_vals:
                # Each distinct non-zero paint value represents a different color group
                # +1 for the unpainted base material
                proxy_count = len(paint_hex_vals) + 1
                # We don't have actual hex codes — return empty colors list
                # but set color_count via the proxy approach (handled in caller)
                result[obj_id] = ([], has_vendor_paint)
                # Store proxy count by overriding the color list with sentinels
                # Caller uses len(colors) when has_vendor_paint; we signal proxy_count
                # by stuffing that many empty strings
                result[obj_id] = ([""] * proxy_count, True)
                continue

        result[obj_id] = (list(collected_colors), has_vendor_paint)

    return result


# ---------------------------------------------------------------------------
# File-level analyzers
# ---------------------------------------------------------------------------


def _check_triangle_cap(path: Path, total_faces: int, max_triangles: int | None) -> None:
    """Raise ``MeshTooLargeError`` when *total_faces* exceeds *max_triangles*.

    A no-op when ``max_triangles`` is None (no cap — existing direct callers of
    ``analyze_file`` are unaffected; see issue #37 fix #4).
    """
    if max_triangles is not None and total_faces > max_triangles:
        raise MeshTooLargeError(
            f"{path.name} has {total_faces:,} triangles "
            f"(cap {max_triangles:,}) — skipping analysis"
        )


def _analyze_stl(
    path: Path,
    density: float,
    infill_pct: float,
    max_triangles: int | None = None,
) -> list[ObjectAnalysis]:
    """STL → single object, 1 color."""
    import trimesh  # noqa: PLC0415

    loaded = trimesh.load(str(path), force="mesh")
    if hasattr(loaded, "geometry"):
        # Unexpected Scene for STL — concatenate
        meshes = list(loaded.geometry.values())
        if not meshes:
            raise ValueError(f"STL loaded as empty Scene: {path.name}")
        mesh = trimesh.util.concatenate(meshes)
    elif hasattr(loaded, "vertices"):
        mesh = loaded
    else:
        raise ValueError(f"Unexpected trimesh type for STL {path.name}: {type(loaded)}")

    _check_triangle_cap(path, len(mesh.faces), max_triangles)

    return [_make_object_result(path.stem, mesh, [], 1, density, infill_pct)]


def _analyze_3mf(
    path: Path,
    density: float,
    infill_pct: float,
    max_triangles: int | None = None,
) -> list[ObjectAnalysis]:
    """3MF → potentially multiple objects; colors from XML via lxml."""
    import trimesh  # noqa: PLC0415
    import trimesh.util  # noqa: PLC0415

    # Parse colors from ZIP XML
    raw_bytes = path.read_bytes()
    color_map = _parse_3mf_colors(raw_bytes)  # {obj_id: ([hex,...], has_vendor_paint)}

    # Load geometry via trimesh
    loaded = trimesh.load(str(path))

    if isinstance(loaded, trimesh.Trimesh):
        _check_triangle_cap(path, len(loaded.faces), max_triangles)
        # Single-body 3MF
        # Try to match by first object in color_map
        obj_ids = list(color_map.keys())
        if obj_ids:
            colors, has_vendor_paint = color_map[obj_ids[0]]
            colors_clean = [c for c in colors if c]
            color_count = len(colors_clean) if colors_clean else (len(colors) if colors else 1)
        else:
            colors_clean = []
            color_count = 1
        name = loaded.metadata.get("name", path.stem) if hasattr(loaded, "metadata") else path.stem
        return [_make_object_result(name, loaded, colors_clean, color_count, density, infill_pct)]

    if not isinstance(loaded, trimesh.Scene):
        raise ValueError(f"Unexpected trimesh result for 3MF {path.name}: {type(loaded)}")

    if not loaded.geometry:
        raise ValueError(f"3MF loaded as empty Scene: {path.name}")

    # Cap check: total triangles across ALL objects in the scene (a many-small-
    # object 3MF can still be a huge overall mesh).
    total_faces = sum(len(m.faces) for m in loaded.geometry.values())
    _check_triangle_cap(path, total_faces, max_triangles)

    # Map geometry names to object ids: trimesh uses metadata or object names
    # Attempt to match color_map keys to geometry names
    geom_items = list(loaded.geometry.items())  # [(name, mesh), ...]
    color_ids = list(color_map.keys())  # XML object ids in order

    objects: list[ObjectAnalysis] = []
    for i, (geom_name, mesh) in enumerate(geom_items):
        # Try to match: trimesh may name geoms as 'object_<id>' or by component name
        matched_colors: list[str] = []
        matched_count = 1

        # Try exact match by object id
        if geom_name in color_map:
            c, _vp = color_map[geom_name]
            matched_colors = [x for x in c if x]
            matched_count = len(c) if c else 1
        # Try stripping common prefix patterns
        elif geom_name.replace("object_", "") in color_map:
            oid = geom_name.replace("object_", "")
            c, _vp = color_map[oid]
            matched_colors = [x for x in c if x]
            matched_count = len(c) if c else 1
        # Fall back to positional match
        elif i < len(color_ids):
            c, _vp = color_map[color_ids[i]]
            matched_colors = [x for x in c if x]
            matched_count = len(c) if c else 1

        final_color_count = len(matched_colors) if matched_colors else matched_count
        objects.append(
            _make_object_result(
                geom_name, mesh, matched_colors, final_color_count, density, infill_pct,
            )
        )

    return objects


def _analyze_generic(
    path: Path,
    density: float,
    infill_pct: float,
    max_triangles: int | None = None,
) -> list[ObjectAnalysis]:
    """OBJ / PLY / other → load, concatenate if multi-body, 1 color."""
    import trimesh  # noqa: PLC0415
    import trimesh.util  # noqa: PLC0415

    loaded = trimesh.load(str(path))

    if isinstance(loaded, trimesh.Scene):
        meshes = list(loaded.geometry.values())
        if not meshes:
            raise ValueError(f"File loaded as empty Scene: {path.name}")
        total_faces = sum(len(m.faces) for m in meshes)
        _check_triangle_cap(path, total_faces, max_triangles)
        # Return each geometry as its own object
        objects: list[ObjectAnalysis] = []
        for name, mesh in loaded.geometry.items():
            objects.append(_make_object_result(name, mesh, [], 1, density, infill_pct))
        return objects

    if isinstance(loaded, trimesh.Trimesh):
        _check_triangle_cap(path, len(loaded.faces), max_triangles)
        return [_make_object_result(path.stem, loaded, [], 1, density, infill_pct)]

    raise ValueError(f"Unexpected trimesh type for {path.name}: {type(loaded)}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def analyze_file(
    path: Path,
    density_g_cm3: float = 1.24,
    infill_pct: float = 15.0,
    source_hash: str | None = None,
    max_triangles: int | None = None,
) -> FileAnalysis:
    """Analyze a mesh file and return a FileAnalysis dict.

    Args:
        path:          Absolute path to the mesh file.
        density_g_cm3: Filament density (g/cm³).  Default 1.24 (PLA).
        infill_pct:    Infill percentage (0–100).  Default 15.
        source_hash:   sha256 of the file bytes; computed here if None.
        max_triangles: Triangle-count cap (issue #37 fix #4).  Meshes with more
                       total faces than this raise ``MeshTooLargeError`` instead
                       of being fully loaded.  ``None`` (default) — no cap, so
                       existing direct callers of ``analyze_file`` are unaffected.

    Returns:
        FileAnalysis dict with 'objects', 'total_objects', 'total_colors',
        'total_est_grams', 'analyzed_at', 'source_hash'.

    Raises:
        ValueError: unsupported extension or failed to load.
        MeshTooLargeError: total triangle count exceeds ``max_triangles``.
        Any trimesh / lxml error is surfaced as-is; callers should wrap in
        try/except and mark the file as unanalyzed.
    """
    if source_hash is None:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        source_hash = h.hexdigest()

    ext = path.suffix.lower()
    if ext not in MESH_ANALYSIS_EXTENSIONS:
        raise ValueError(f"Unsupported extension for analysis: {ext!r}")

    if ext == ".stl":
        objects = _analyze_stl(path, density_g_cm3, infill_pct, max_triangles)
    elif ext == ".3mf":
        objects = _analyze_3mf(path, density_g_cm3, infill_pct, max_triangles)
    else:
        objects = _analyze_generic(path, density_g_cm3, infill_pct, max_triangles)

    # Aggregate totals
    all_colors: set[str] = set()
    total_color_count = 0
    total_grams = 0.0
    for obj in objects:
        hex_colors = [c for c in obj.get("colors", []) if c]
        if hex_colors:
            all_colors.update(hex_colors)
        else:
            total_color_count += obj.get("color_count", 1)
        g = obj.get("est_grams")
        if g is not None:
            total_grams += g

    total_colors = len(all_colors) if all_colors else total_color_count

    return {
        "analyzed_at": datetime.now(UTC).isoformat(),
        "source_hash": source_hash,
        "objects": objects,
        "total_objects": len(objects),
        "total_colors": total_colors,
        "total_est_grams": round(total_grams, 3),
    }
