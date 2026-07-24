"""3MF reader — thumbnail extraction + slicer metadata (no GL required).

Reads a .3mf file (ZIP) to extract:
  - The best embedded thumbnail (Metadata/plate_1.png preferred).
  - Whether the file has been sliced (gcode present).
  - Per-plate print time, filament weight, and per-filament detail.
  - Slicer name/version and printer model from project settings.

This is intentionally kept GL-free (no trimesh, no VTK). It handles the
common Bambu/OrcaSlicer 3MF format; standard 3MF files without Bambu
extensions will parse cleanly with zero slicer metadata (sliced=False,
all optional fields None).

Never raises on malformed/partial 3MF — returns whatever could be parsed.

Return schema (all fields always present; optional ones may be None):
{
    'thumbnail_bytes': bytes | None,
    'thumbnail_entry': str | None,      # ZIP entry name that was extracted
    'sliced': bool,
    'slicer': str | None,               # e.g. "BambuStudio 01.09.05"
    'printer_model': str | None,
    'plate_count': int,
    'objects_total': int,               # 0 = could not determine
    'print_time_s': int | None,         # total across all plates
    'total_filament_g': float | None,   # total across all filaments/plates
    'filament': [
        {
            'slot': int,                # 1-indexed filament slot
            'type': str | None,         # e.g. "PLA"
            'color_hex': str | None,    # e.g. "#FF0000"
            'used_g': float | None,
            'used_m': float | None,
        },
        ...
    ],
    'plates': [
        {
            'index': int,
            'print_time_s': int | None,
            'weight_g': float | None,
        },
        ...
    ],
}
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Thumbnail candidates in preference order; both .png and .jpg accepted.
_THUMB_CANDIDATES = [
    "Metadata/plate_1.png",
    "Metadata/plate_1.jpg",
    "Metadata/top_plate_1.png",
    "Metadata/top_plate_1.jpg",
    "Metadata/thumbnail.png",
    "Metadata/thumbnail.jpg",
    "Metadata/thumbnail_small.png",
    "Metadata/thumbnail_small.jpg",
]

# 3MF core namespace
_NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"

# Gcode entry pattern: Metadata/plate_<N>.gcode (or .gcode.gz etc.)
_GCODE_RE = re.compile(r"^Metadata/plate_\d+\.gcode", re.IGNORECASE)

FilamentEntry = dict[str, Any]
PlateEntry = dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hardened_parser(etree: Any) -> Any:
    """Return an lxml parser hardened for untrusted 3MF XML.

    .3mf payloads are user-supplied, so entity resolution, network access, DTD
    loading/validation, and huge-tree parsing are all disabled to neutralise
    XXE / entity-expansion / SSRF-via-DTD vectors. lxml's defaults already
    block most of these; this makes the intent explicit and fail-closed.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )


def _best_thumbnail(zf: zipfile.ZipFile) -> tuple[bytes | None, str | None]:
    """Return (raw_bytes, entry_name) for the best available thumbnail in zf."""
    names_lower: dict[str, str] = {n.lower(): n for n in zf.namelist()}
    for candidate in _THUMB_CANDIDATES:
        actual = names_lower.get(candidate.lower())
        if actual is not None:
            try:
                data = zf.read(actual)
                if data:
                    return data, actual
            except Exception as exc:
                log.debug("threemf: error reading thumbnail %s: %s", actual, exc)
    return None, None


def _detect_sliced(zf: zipfile.ZipFile) -> bool:
    """Return True if the ZIP contains any gcode file entries."""
    for name in zf.namelist():
        if _GCODE_RE.match(name):
            return True
    return False


def _parse_slice_info(zf: zipfile.ZipFile) -> tuple[list[PlateEntry], list[FilamentEntry]]:
    """Parse Metadata/slice_info.config (Bambu/Orca XML).

    Returns (plates, filaments) where filaments are merged across all plates
    (slot de-duplicated, last plate's data wins for a given slot).
    Returns ([], []) on any error or if the file is absent.
    """
    try:
        from lxml import etree  # noqa: PLC0415
    except ImportError:
        log.debug("threemf: lxml not available; slice_info not parsed")
        return [], []

    names_lower = {n.lower(): n for n in zf.namelist()}
    entry = names_lower.get("metadata/slice_info.config")
    if entry is None:
        return [], []

    try:
        data = zf.read(entry)
        root = etree.fromstring(data, _hardened_parser(etree))  # type: ignore[attr-defined]
    except Exception as exc:
        log.debug("threemf: could not parse slice_info.config: %s", exc)
        return [], []

    plates: list[PlateEntry] = []
    filament_by_slot: dict[int, FilamentEntry] = {}

    for plate_el in root.findall("plate"):
        plate_index: int | None = None
        print_time_s: int | None = None
        weight_g: float | None = None

        for meta in plate_el.findall("metadata"):
            key = meta.get("key", "")
            val = meta.get("value", "")
            if key == "index":
                try:
                    plate_index = int(val)
                except (ValueError, TypeError):
                    pass
            elif key == "prediction":
                try:
                    print_time_s = int(float(val))
                except (ValueError, TypeError):
                    pass
            elif key == "weight":
                try:
                    weight_g = float(val)
                except (ValueError, TypeError):
                    pass

        plates.append(
            {
                "index": plate_index if plate_index is not None else len(plates) + 1,
                "print_time_s": print_time_s,
                "weight_g": weight_g,
            }
        )

        # Per-filament rows within this plate
        for fil_el in plate_el.findall("filament"):
            try:
                slot = int(fil_el.get("id", "0"))
            except (ValueError, TypeError):
                slot = 0

            fil_type = fil_el.get("type") or None
            # BambuStudio stores colour in "color"; OrcaSlicer may use "colour"
            color_raw = fil_el.get("color") or fil_el.get("colour") or None
            color_hex: str | None = None
            if color_raw:
                color_hex = color_raw.strip().upper()
                if not color_hex.startswith("#"):
                    color_hex = "#" + color_hex

            used_m: float | None = None
            used_g: float | None = None
            try:
                used_m = float(fil_el.get("used_m", "") or "")
            except (ValueError, TypeError):
                pass
            try:
                used_g = float(fil_el.get("used_g", "") or "")
            except (ValueError, TypeError):
                pass

            if slot not in filament_by_slot or used_g is not None:
                filament_by_slot[slot] = {
                    "slot": slot,
                    "type": fil_type,
                    "color_hex": color_hex,
                    "used_g": used_g,
                    "used_m": used_m,
                }

    filaments = sorted(filament_by_slot.values(), key=lambda f: f["slot"])
    return plates, filaments


def _parse_project_settings(
    zf: zipfile.ZipFile,
) -> tuple[str | None, str | None, list[str], list[str]]:
    """Parse Metadata/project_settings.config (Bambu/Orca JSON).

    Returns (slicer_str, printer_model, filament_colour_list, filament_type_list).
    Returns (None, None, [], []) on any error or if absent.
    """
    names_lower = {n.lower(): n for n in zf.namelist()}
    entry = names_lower.get("metadata/project_settings.config")
    if entry is None:
        return None, None, [], []

    try:
        data = zf.read(entry)
        cfg = json.loads(data)
    except Exception as exc:
        log.debug("threemf: could not parse project_settings.config: %s", exc)
        return None, None, [], []

    if not isinstance(cfg, dict):
        return None, None, [], []

    # Slicer string: try common locations
    slicer: str | None = None
    printer_model: str | None = None
    filament_colours: list[str] = []
    filament_types: list[str] = []

    try:
        printer_model = cfg.get("printer_model") or cfg.get("machine") or None
        if isinstance(printer_model, str):
            printer_model = printer_model.strip() or None
    except Exception:
        pass

    # filament_colour / filament_color
    try:
        cols = cfg.get("filament_colour") or cfg.get("filament_color") or []
        if isinstance(cols, list):
            filament_colours = [str(c).strip().upper() for c in cols if c]
    except Exception:
        pass

    try:
        types = cfg.get("filament_type") or []
        if isinstance(types, list):
            filament_types = [str(t).strip() for t in types if t]
    except Exception:
        pass

    # Slicer version
    try:
        # BambuStudio puts version in the "version" field (numeric string)
        # and the slicer name is inferred from the file header or metadata
        ver = cfg.get("version") or cfg.get("slicer_version") or ""
        name_field = cfg.get("slicer_name") or cfg.get("slicer") or ""
        if name_field and ver:
            slicer = f"{name_field} {ver}".strip()
        elif name_field:
            slicer = str(name_field).strip() or None
        elif ver:
            # Try to infer slicer name from 3dmodel.model application attribute
            slicer = str(ver).strip() or None
    except Exception:
        pass

    return slicer, printer_model, filament_colours, filament_types


def _count_objects_from_model(zf: zipfile.ZipFile) -> int:
    """Count mesh objects in 3D/3dmodel.model; return 0 on any failure."""
    try:
        from lxml import etree  # noqa: PLC0415
    except ImportError:
        return 0

    names_lower = {n.lower(): n for n in zf.namelist()}
    entry = names_lower.get("3d/3dmodel.model")
    if entry is None:
        return 0

    try:
        data = zf.read(entry)
        root = etree.fromstring(data, _hardened_parser(etree))  # type: ignore[attr-defined]
    except Exception:
        return 0

    resources = root.find(f"{{{_NS_3MF}}}resources")
    if resources is None:
        return 0

    count = 0
    for obj in resources.findall(f"{{{_NS_3MF}}}object"):
        obj_type = obj.get("type", "model")
        # count only printable objects (model), not support structures etc.
        if obj_type in ("model", "") or obj_type is None:
            mesh = obj.find(f"{{{_NS_3MF}}}mesh")
            if mesh is not None:
                count += 1
    return max(count, 0)


def _parse_model_settings(zf: zipfile.ZipFile) -> int:
    """Best-effort parse of Metadata/model_settings.config for object count.

    Returns the count of named objects from the config; 0 if absent or
    unparseable.
    """
    try:
        from lxml import etree  # noqa: PLC0415
    except ImportError:
        return 0

    names_lower = {n.lower(): n for n in zf.namelist()}
    entry = names_lower.get("metadata/model_settings.config")
    if entry is None:
        return 0

    try:
        data = zf.read(entry)
        root = etree.fromstring(data, _hardened_parser(etree))  # type: ignore[attr-defined]
    except Exception:
        return 0

    count = 0
    # BambuStudio model_settings: <object id="..." name="..."> elements
    for _obj in root.findall(".//object"):
        count += 1
    return count


def _enrich_filaments_from_project(
    filaments: list[FilamentEntry],
    fil_colours: list[str],
    fil_types: list[str],
) -> list[FilamentEntry]:
    """Fill in color_hex / type from project_settings when slice_info lacks them."""
    result: list[FilamentEntry] = []
    for fil in filaments:
        slot = fil["slot"]
        idx = slot - 1  # project_settings arrays are 0-indexed, slot is 1-indexed
        f = dict(fil)
        if f.get("color_hex") is None and 0 <= idx < len(fil_colours):
            raw = fil_colours[idx]
            f["color_hex"] = (raw if raw.startswith("#") else "#" + raw) if raw else None
        if f.get("type") is None and 0 <= idx < len(fil_types):
            f["type"] = fil_types[idx] or None
        result.append(f)
    return result


# ---------------------------------------------------------------------------
# Structural validation (reconcile integrity check — corruption vs legit edit)
# ---------------------------------------------------------------------------


def validate_3mf_structure(path: Path, max_xml_mb: int | None = None) -> bool:
    """Return True if *path* is a structurally valid 3MF.

    Unlike ``read_3mf`` (which never raises and always returns a best-effort
    default dict — it is used for optional metadata extraction), this is a
    strict structural check used by the reconcile integrity behavior
    (``worker/reconcile.py``) to tell a legitimate in-place slicer re-save
    (still parses) apart from a truncated/interrupted write (does not parse).
    See docs/decisions.md for the false-corruption bug this closes.

    Checks, in order:
      1. The file opens as a ZIP (``zipfile.BadZipFile`` → False).
      2. It contains a ``3D/3dmodel.model`` entry (missing → False).
      3. That entry's uncompressed size is within *max_xml_mb* (mirrors the
         pre-load guard in ``mesh_analysis._check_3mf_xml_size`` — issue #37
         follow-up: a huge geometry-XML part can balloon ~15-20x once parsed
         into an lxml DOM). When the cap is exceeded, parsing is skipped and
         this returns True — we deliberately do not risk ballooning memory
         just to answer a corruption question; a hostile/huge file is a
         separate, already-guarded concern for the actual analyze/render
         pipelines, not something this cheap check should attempt itself.
      4. The entry parses as well-formed XML (via the same hardened parser
         used elsewhere in this module) with a ``model`` root element in the
         3MF core namespace.

    A no-op cap (``max_xml_mb=None``) always parses (used by callers, e.g.
    unit tests, that don't have a configured limit).
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return False

    try:
        with zipfile.ZipFile(BytesIO(raw)) as zf:
            names_lower = {n.lower(): n for n in zf.namelist()}
            entry = names_lower.get("3d/3dmodel.model")
            if entry is None:
                return False

            info = zf.getinfo(entry)
            if max_xml_mb is not None and info.file_size > max_xml_mb * 1024 * 1024:
                log.info(
                    "threemf.validate_3mf_structure: %s geometry part exceeds "
                    "%d MB cap; skipping parse (assumed valid)",
                    path.name, max_xml_mb,
                )
                return True

            try:
                from lxml import etree  # noqa: PLC0415
            except ImportError:
                # lxml unavailable — fall back to "zip opens + part present".
                log.warning(
                    "threemf.validate_3mf_structure: lxml not available; "
                    "%s validated by ZIP structure only",
                    path.name,
                )
                return True

            data = zf.read(entry)
            root = etree.fromstring(data, _hardened_parser(etree))  # type: ignore[attr-defined]
            return bool(root.tag == f"{{{_NS_3MF}}}model")
    except zipfile.BadZipFile as exc:
        log.info("threemf.validate_3mf_structure: %s is not a valid ZIP: %s", path.name, exc)
        return False
    except Exception as exc:
        log.warning("threemf.validate_3mf_structure: %s failed to parse: %s", path.name, exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_3mf(path: Path) -> dict[str, Any]:
    """Read a .3mf file and return thumbnail + slicer metadata.

    Never raises — returns a safe default dict on any error.

    Args:
        path: Absolute path to the .3mf file.

    Returns:
        Dict with keys: thumbnail_bytes, thumbnail_entry, sliced, slicer,
        printer_model, plate_count, objects_total, print_time_s,
        total_filament_g, filament, plates.
    """
    default: dict[str, Any] = {
        "thumbnail_bytes": None,
        "thumbnail_entry": None,
        "sliced": False,
        "slicer": None,
        "printer_model": None,
        "plate_count": 0,
        "objects_total": 0,
        "print_time_s": None,
        "total_filament_g": None,
        "filament": [],
        "plates": [],
    }

    try:
        raw = path.read_bytes()
    except OSError as exc:
        log.warning("threemf.read_3mf: cannot read %s: %s", path, exc)
        return default

    try:
        with zipfile.ZipFile(BytesIO(raw)) as zf:
            # 1. Thumbnail
            thumb_bytes, thumb_entry = _best_thumbnail(zf)

            # 2. Sliced detection
            sliced = _detect_sliced(zf)

            # 3. Slice info (per-plate time/weight/filament)
            plates, filaments = _parse_slice_info(zf)

            # Also check model_settings.config for gcode_file (alternative sliced detection)
            if not sliced:
                try:
                    from lxml import etree  # noqa: PLC0415

                    names_lower = {n.lower(): n for n in zf.namelist()}
                    ms_entry = names_lower.get("metadata/model_settings.config")
                    if ms_entry:
                        ms_data = zf.read(ms_entry)
                        ms_root = etree.fromstring(ms_data, _hardened_parser(etree))  # type: ignore[attr-defined]
                        for meta in ms_root.findall(".//metadata"):
                            if meta.get("key") == "gcode_file" and meta.get("value"):
                                sliced = True
                                break
                except Exception:
                    pass

            # 4. Project settings (slicer info + colours)
            slicer, printer_model, fil_colours, fil_types = _parse_project_settings(zf)

            # 5. Object count
            obj_count = _count_objects_from_model(zf)
            if obj_count == 0:
                obj_count = _parse_model_settings(zf)

            # Enrich filaments with project_settings colour/type data
            if filaments and (fil_colours or fil_types):
                filaments = _enrich_filaments_from_project(filaments, fil_colours, fil_types)

            # Compute aggregates
            plate_count = len(plates) if plates else (1 if sliced else 0)

            total_time_s: int | None = None
            for p in plates:
                t = p.get("print_time_s")
                if t is not None:
                    total_time_s = (total_time_s or 0) + t

            total_g: float | None = None
            for fil in filaments:
                g = fil.get("used_g")
                if g is not None:
                    total_g = (total_g or 0.0) + g

            return {
                "thumbnail_bytes": thumb_bytes,
                "thumbnail_entry": thumb_entry,
                "sliced": sliced,
                "slicer": slicer,
                "printer_model": printer_model,
                "plate_count": plate_count,
                "objects_total": obj_count,
                "print_time_s": total_time_s,
                "total_filament_g": total_g,
                "filament": filaments,
                "plates": plates,
            }

    except zipfile.BadZipFile as exc:
        log.warning("threemf.read_3mf: %s is not a valid ZIP: %s", path.name, exc)
        return default
    except Exception as exc:
        log.warning("threemf.read_3mf: unexpected error reading %s: %s", path.name, exc)
        return default
