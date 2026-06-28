"""gcode metadata parser — Phase 7 (PRD §9.1).

Parses slicer comment headers best-effort for:
  - filament required (length mm, weight g)
  - estimated print time (seconds)

Handles four slicer dialects:
  Prusa Slicer:    ; filament used [mm] = X
                   ; filament used [g] = X
                   ; estimated printing time (normal mode) = Xh Ym Zs
  Orca Slicer:     ; filament used [mm] = X  (same as Prusa)
                   ; filament used [g] = X
                   ; total estimated time = Xh Ym Zs
  Cura:            ;Filament used: X.XXm   (meters — converted to mm)
                   ;TIME:X                 (seconds, integer)
  Bambu Studio:    ; total filament used [g] = X
                   ; total estimated time = Xh Ym Zs
                   ;totalTime:X            (seconds, integer)

All fields are best-effort: missing data returns None for that field.
Binary formats (.bgcode) are returned as empty GcodeMetadata gracefully.

Only the first MAX_HEADER_BYTES bytes of the file are read.  This is sufficient
because all slicer dialects write their metadata in the header.

This module is purely functional — no DB, no filesystem side effects.  All parsing
happens in parse_gcode_text() which takes a string, enabling unit testing with
inline fixtures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Read only the first 32 KB — all slicer headers fit in this window.
MAX_HEADER_BYTES = 32_768

# Extensions we can parse as text.  bgcode is binary — skip gracefully.
PARSEABLE_GCODE_EXTENSIONS = frozenset({".gcode", ".gco"})


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class GcodeMetadata:
    """Parsed gcode metadata — all fields are best-effort / nullable."""

    filament_length_mm: float | None = None
    filament_weight_g: float | None = None
    estimated_print_time_s: int | None = None
    slicer: str | None = None  # "prusa" | "orca" | "cura" | "bambu" | None
    parse_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_gcode_file(path: Path) -> GcodeMetadata:
    """Parse a gcode file on disk.

    Returns an empty GcodeMetadata if the file is binary (bgcode) or unreadable.
    Never raises.
    """
    suffix = path.suffix.lower()
    if suffix not in PARSEABLE_GCODE_EXTENSIONS:
        # Binary format (bgcode) or unknown — return empty without error
        return GcodeMetadata()

    try:
        with path.open("rb") as fh:
            raw = fh.read(MAX_HEADER_BYTES)
        text = raw.decode("utf-8", errors="ignore")
    except OSError as exc:
        return GcodeMetadata(parse_errors=[f"Could not read file: {exc}"])

    return parse_gcode_text(text)


def parse_gcode_text(text: str) -> GcodeMetadata:
    """Parse gcode metadata from a text string.

    Pure function — no I/O.  Useful for unit testing with inline fixtures.
    """
    meta = GcodeMetadata()
    lines = text.splitlines()
    comment_lines = [ln for ln in lines if ln.startswith(";")]

    _detect_slicer(meta, comment_lines)
    _parse_filament_mm(meta, comment_lines)
    _parse_filament_g(meta, comment_lines)
    if meta.filament_length_mm is None:
        _parse_cura_filament_m(meta, comment_lines)
    _parse_print_time(meta, comment_lines, lines)

    return meta


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# --- Slicer detection ---

_SLICER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"prusaslicer|prusa slicer", re.IGNORECASE), "prusa"),
    (re.compile(r"orcaslicer|orca slicer", re.IGNORECASE), "orca"),
    (re.compile(r"bambu studio|bambu", re.IGNORECASE), "bambu"),
    (re.compile(r"cura", re.IGNORECASE), "cura"),
]


def _detect_slicer(meta: GcodeMetadata, comment_lines: list[str]) -> None:
    # Only inspect the first 30 comment lines — the generator line is near the top.
    for line in comment_lines[:30]:
        for pattern, name in _SLICER_PATTERNS:
            if pattern.search(line):
                meta.slicer = name
                return


# --- Filament length (mm) ---

# Prusa/Orca/Bambu: ; [total ]filament used [mm] = 1234.56
_RE_FILAMENT_MM = re.compile(
    r";\s*(?:total\s+)?filament\s+used\s*\[mm\]\s*=\s*([\d.]+)",
    re.IGNORECASE,
)


def _parse_filament_mm(meta: GcodeMetadata, comment_lines: list[str]) -> None:
    for line in comment_lines:
        m = _RE_FILAMENT_MM.search(line)
        if m:
            try:
                meta.filament_length_mm = float(m.group(1))
                return
            except ValueError:
                pass


# --- Filament weight (g) ---

# Prusa/Orca/Bambu: ; [total ]filament used [g] = 6.78
_RE_FILAMENT_G = re.compile(
    r";\s*(?:total\s+)?filament\s+used\s*\[g\]\s*=\s*([\d.]+)",
    re.IGNORECASE,
)


def _parse_filament_g(meta: GcodeMetadata, comment_lines: list[str]) -> None:
    for line in comment_lines:
        m = _RE_FILAMENT_G.search(line)
        if m:
            try:
                meta.filament_weight_g = float(m.group(1))
                return
            except ValueError:
                pass


# --- Cura filament (meters → mm) ---

# Cura: ;Filament used: 1.23m
_RE_CURA_FILAMENT_M = re.compile(
    r";\s*[Ff]ilament\s+used\s*:\s*([\d.]+)\s*m\b",
    re.IGNORECASE,
)


def _parse_cura_filament_m(meta: GcodeMetadata, comment_lines: list[str]) -> None:
    for line in comment_lines:
        m = _RE_CURA_FILAMENT_M.search(line)
        if m:
            try:
                meta.filament_length_mm = float(m.group(1)) * 1000.0
                return
            except ValueError:
                pass


# --- Print time ---

# Prusa:  ; estimated printing time (normal mode) = 2h 3m 45s
# Orca:   ; total estimated time = 1h 2m 30s
# Bambu:  ; total estimated time = 1h 2m 30s  (same pattern)
_RE_TIME_COMMENT = re.compile(
    r";\s*(?:estimated\s+printing\s+time.*?|total\s+estimated\s+time)\s*=\s*(.+)",
    re.IGNORECASE,
)

# Bambu binary-style: ;totalTime:3600
_RE_BAMBU_TOTAL_TIME = re.compile(r";\s*totalTime\s*:\s*(\d+)", re.IGNORECASE)

# Cura: ;TIME:7890  (seconds integer, at the very start of a line)
_RE_CURA_TIME = re.compile(r"^;TIME\s*:\s*(\d+)", re.IGNORECASE)


def _parse_print_time(
    meta: GcodeMetadata,
    comment_lines: list[str],
    all_lines: list[str],
) -> None:
    # 1. Prusa / Orca / Bambu time string
    for line in comment_lines:
        m = _RE_TIME_COMMENT.search(line)
        if m:
            secs = _parse_time_str(m.group(1).strip())
            if secs is not None:
                meta.estimated_print_time_s = secs
                return

    # 2. Bambu ;totalTime:X  (integer seconds)
    for line in comment_lines:
        m = _RE_BAMBU_TOTAL_TIME.search(line)
        if m:
            meta.estimated_print_time_s = int(m.group(1))
            return

    # 3. Cura ;TIME:X  (integer seconds, at line start)
    for line in all_lines:
        m = _RE_CURA_TIME.match(line)
        if m:
            meta.estimated_print_time_s = int(m.group(1))
            return


# --- Time string parser ---


def _parse_time_str(s: str) -> int | None:
    """Parse a human-readable time string into seconds.

    Examples:
      "2h 3m 45s" → 7425
      "1h 2m"     → 3720
      "45s"       → 45
      "1d 2h"     → 93600
    """
    total = 0
    found = False

    d_m = re.search(r"(\d+)\s*d", s, re.IGNORECASE)
    h_m = re.search(r"(\d+)\s*h", s, re.IGNORECASE)
    m_m = re.search(r"(\d+)\s*m(?!s)", s, re.IGNORECASE)  # 'm' not followed by 's' (ms)
    s_m = re.search(r"(\d+)\s*s\b", s, re.IGNORECASE)

    if d_m:
        total += int(d_m.group(1)) * 86400
        found = True
    if h_m:
        total += int(h_m.group(1)) * 3600
        found = True
    if m_m:
        total += int(m_m.group(1)) * 60
        found = True
    if s_m:
        total += int(s_m.group(1))
        found = True

    return total if found else None
