"""File inventory and SHA-256 hashing for an item directory.

Walks the item directory and records each file as a File row.

Role inference (docs/sidecar-schema.md §1 + PRD §4):
- Files inside renders/      → render
- Files inside images/       → image
- Files inside prints/       with .gcode/.gco extension → gcode
- Files inside prints/       with photo extensions      → photo
- Files at any depth with model extensions             → model
- Files with .zip extension                            → zip
- Anything else                                        → other

The sidecar file itself (<slug>-<key>.yml) is excluded from the inventory.

Cheap-first drift check (sidecar-schema.md §1 hashing policy):
Treat a file as unchanged when BOTH size AND mtime match the stored
(last_seen_size, last_seen_mtime) snapshot.  Only re-hash when they differ or
on an explicit integrity/Rescan pass.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

from ..models.file import FileRole

# ---------------------------------------------------------------------------
# Extension sets
# ---------------------------------------------------------------------------

MODEL_EXTENSIONS = frozenset({
    ".stl", ".3mf", ".obj", ".ply", ".blend", ".f3d",
    ".step", ".stp", ".fcstd", ".amf", ".dae",
})

PHOTO_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
})

GCODE_EXTENSIONS = frozenset({".gcode", ".gco", ".bgcode"})


# ---------------------------------------------------------------------------
# Role inference
# ---------------------------------------------------------------------------

def infer_role(relative_path: str) -> FileRole:
    """Infer the FileRole for a file given its path relative to the item dir.

    Evaluated top-down (first match wins).
    """
    parts = Path(relative_path).parts  # ('renders', 'thumb.png') etc.
    ext = Path(relative_path).suffix.lower()

    if len(parts) >= 2:
        top_dir = parts[0].lower()
        if top_dir == "renders":
            return FileRole.render
        if top_dir == "images":
            return FileRole.image
        if top_dir == "prints":
            if ext in GCODE_EXTENSIONS:
                return FileRole.gcode
            if ext in PHOTO_EXTENSIONS:
                return FileRole.photo
            return FileRole.other

    if ext in MODEL_EXTENSIONS:
        return FileRole.model
    if ext == ".zip":
        return FileRole.zip
    if ext in PHOTO_EXTENSIONS:
        return FileRole.image

    return FileRole.other


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def hash_file_sha256(path: Path, chunk_size: int = 65536) -> str:
    """Compute the SHA-256 hex digest of a file (lowercase)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Inventory result
# ---------------------------------------------------------------------------

class FileRecord:
    """Transient file record returned from inventory_item()."""

    __slots__ = ("relative_path", "role", "size", "sha256", "mtime")

    def __init__(
        self,
        relative_path: str,
        role: FileRole,
        size: int,
        sha256: str,
        mtime: datetime,
    ) -> None:
        self.relative_path = relative_path
        self.role = role
        self.size = size
        self.sha256 = sha256
        self.mtime = mtime


# ---------------------------------------------------------------------------
# Main inventory function
# ---------------------------------------------------------------------------

def _mtime_utc(stat_result: os.stat_result) -> datetime:
    """Extract mtime from a stat result as a UTC-aware datetime."""
    return datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)


def inventory_item(
    item_dir: Path,
    sidecar_filename: str,
    existing: dict[str, tuple[int, datetime, str | None]] | None = None,
    force_rehash: bool = False,
) -> list[FileRecord]:
    """Walk item_dir and return a FileRecord for every file (excluding sidecar).

    Args:
        item_dir:         Absolute path to the item directory.
        sidecar_filename: Name of the sidecar YAML file to exclude.
        existing:         Map from relative_path → (size, mtime, sha256) for
                          cheap-first drift checking.  Pass None to always hash.
        force_rehash:     If True, always recompute SHA-256 regardless of drift.

    Returns:
        List of FileRecord, one per file found on disk.
    """
    records: list[FileRecord] = []

    if not item_dir.is_dir():
        return records

    for entry in sorted(item_dir.rglob("*")):
        if not entry.is_file():
            continue

        # Exclude the sidecar itself from the file inventory.
        if entry.name == sidecar_filename:
            continue

        stat = entry.stat()
        size = stat.st_size
        mtime = _mtime_utc(stat)
        rel = str(entry.relative_to(item_dir))

        role = infer_role(rel)

        # Cheap-first drift check
        sha256: str | None = None
        if existing and rel in existing and not force_rehash:
            prev_size, prev_mtime, prev_sha256 = existing[rel]
            if (
                size == prev_size
                and abs((mtime - prev_mtime).total_seconds()) < 1.0
                and prev_sha256 is not None
            ):
                sha256 = prev_sha256  # no re-hash needed

        if sha256 is None:
            sha256 = hash_file_sha256(entry)

        records.append(FileRecord(
            relative_path=rel,
            role=role,
            size=size,
            sha256=sha256,
            mtime=mtime,
        ))

    return records
