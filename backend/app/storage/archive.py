"""Safe ZIP extractor for item directories.

Extracts a ZIP archive into a destination directory with:
- Zip-slip protection (reject entries that escape dest_dir)
- Junk filtering (__MACOSX/, .DS_Store, Thumbs.db, desktop.ini)
- No nested archive recursion (.zip entries are extracted as plain files)
- Configurable caps (uncompressed MB, file count, per-entry size, zip-bomb ratio)
- Lone top-level wrapper folder stripping
- Collision-safe renaming on conflicts
- Clean failure: caps are checked in a pre-scan phase (from the central-directory
  declared sizes) AND re-enforced with a running byte budget during the actual
  decompression, so a crafted ZIP that under-declares its sizes cannot slip past
  the caps. dest_dir is never partially written on cap-exceeded errors: in-flight
  files land in a temp dir and are only moved into dest_dir once every entry has
  been written within budget.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Default caps — overridable via Settings attributes
_DEFAULT_MAX_UNCOMPRESSED_MB = 2048
_DEFAULT_MAX_FILES = 10_000
# Per-entry sanity cap: reject any single entry claiming > 512 MB uncompressed.
_PER_ENTRY_MAX_MB = 512
# Zip-bomb guard: bail if (total uncompressed) / (total compressed) exceeds this.
_BOMB_RATIO = 200
# Chunk size for the runtime byte-budget copy loop.
_COPY_CHUNK_BYTES = 1024 * 1024

# Junk: top-level directory names to skip entirely
_JUNK_TOP_DIRS: frozenset[str] = frozenset({"__MACOSX"})
# Junk: individual filenames (any depth) to skip
_JUNK_NAMES: frozenset[str] = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ExtractResult:
    """Outcome of a single ZIP extraction call."""

    extracted: list[str] = field(default_factory=list)
    """Relative paths (from dest_dir) of files written to disk."""
    skipped: list[str] = field(default_factory=list)
    """Entries skipped (junk, zip-slip, over per-entry cap, empty prefix strip, …)."""
    errors: list[str] = field(default_factory=list)
    """Per-entry I/O errors (non-fatal; extraction of other entries continues)."""


# ---------------------------------------------------------------------------
# Hard error
# ---------------------------------------------------------------------------


class ArchiveError(Exception):
    """Raised when extraction must abort (unreadable ZIP or cap exceeded).

    When this is raised no files have been written to dest_dir.
    """


class _CapExceeded(Exception):
    """Internal: raised by the copy loop when real decompressed bytes blow a cap.

    Caught inside extract_zip and re-raised as ArchiveError so extraction aborts
    (rather than being swallowed by the per-entry recoverable-error handler).
    """


def _copy_within_budget(
    src: object,
    dst: object,
    per_entry_bytes: int,
    total_remaining: int,
) -> int:
    """Copy *src* → *dst* counting real bytes, aborting when a cap is exceeded.

    Streams the decompressed entry in chunks and tracks the actual number of
    bytes produced (which — for a crafted archive — may exceed the size declared
    in the central directory). Raises _CapExceeded the moment this entry passes
    *per_entry_bytes* or its bytes would push the archive past *total_remaining*
    (the uncompressed budget still available across the whole archive).

    Returns the number of bytes written on success.
    """
    written = 0
    while True:
        chunk = src.read(_COPY_CHUNK_BYTES)  # type: ignore[attr-defined]
        if not chunk:
            break
        written += len(chunk)
        if written > per_entry_bytes:
            raise _CapExceeded(
                f"entry exceeded per-entry cap of {per_entry_bytes // (1024 * 1024)} MB "
                f"during decompression (declared size was smaller)"
            )
        if written > total_remaining:
            raise _CapExceeded(
                "archive exceeded total uncompressed cap during decompression "
                "(declared sizes were smaller)"
            )
        dst.write(chunk)  # type: ignore[attr-defined]
    return written


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_junk(name: str) -> bool:
    """Return True when the ZIP entry should be skipped as junk."""
    parts = Path(name.replace("\\", "/")).parts
    if not parts:
        return True
    # Any path whose first component is a junk directory
    if parts[0] in _JUNK_TOP_DIRS:
        return True
    # Any path whose final component is a junk filename
    if parts[-1] in _JUNK_NAMES:
        return True
    return False


def _safe_dest_rel(raw: str, dest_dir: Path) -> str | None:
    """Validate and normalise an entry name for extraction under dest_dir.

    Returns the normalised relative-path string, or None when the entry
    would escape dest_dir (zip-slip / absolute path / Windows drive letter).
    """
    # Normalise path separators
    name = raw.replace("\\", "/")
    # Reject absolute paths and Windows drive letters
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
        return None
    try:
        candidate = (dest_dir / name).resolve()
        candidate.relative_to(dest_dir.resolve())
    except (ValueError, OSError):
        return None
    return name


def _lone_wrapper_prefix(names: list[str]) -> str | None:
    """Return the lone top-level directory to strip, or None.

    If every entry in *names* starts with the same single directory component,
    and at least one entry has a second component (i.e., it is not just the
    bare directory name), return that component so callers can drop it.
    """
    if not names:
        return None
    top: set[str] = set()
    for n in names:
        parts = Path(n.replace("\\", "/")).parts
        if parts:
            top.add(parts[0])
    if len(top) != 1:
        return None
    prefix = next(iter(top))
    # Ensure at least one entry has a second level (not a single bare file)
    for n in names:
        parts = Path(n.replace("\\", "/")).parts
        if len(parts) >= 2:
            return prefix
    return None


def _collision_rename(rel: str, used: set[str]) -> str:
    """Return a variant of *rel* that is not in *used*.

    Strategy: ``<stem> (<n>)<suffix>`` counting from 1 upward.
    Works for paths with subdirectories (only the final filename is renamed).
    """
    if rel not in used:
        return rel
    p = Path(rel)
    stem = p.stem
    suffix = p.suffix
    parent_str = str(p.parent) if str(p.parent) != "." else ""
    n = 1
    while True:
        new_name = f"{stem} ({n}){suffix}"
        candidate = f"{parent_str}/{new_name}" if parent_str else new_name
        if candidate not in used:
            return candidate
        n += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_zip(
    zip_path: Path,
    dest_dir: Path,
    *,
    existing_paths: set[str] | None = None,
    max_uncompressed_mb: int | None = None,
    max_files: int | None = None,
) -> ExtractResult:
    """Extract *zip_path* into *dest_dir* safely.

    All filtering, cap checking, and collision detection happens in a pre-scan
    phase **before** any bytes are written to *dest_dir*.  A temporary
    directory (sibling of *dest_dir*) holds in-flight files so that even an
    unexpected mid-extraction crash leaves *dest_dir* in a consistent state.

    Args:
        zip_path:            Path to the source ZIP file.
        dest_dir:            Target directory (must already exist).
        existing_paths:      Set of relative paths already present in dest_dir
                             used for collision detection (pass None == empty).
        max_uncompressed_mb: Override the uncompressed-size cap (default 2048 MB).
        max_files:           Override the file-count cap (default 10 000).

    Returns:
        ExtractResult — lists of extracted / skipped / per-entry-error paths.

    Raises:
        ArchiveError: unreadable ZIP, file-count cap, size cap, or bomb ratio
                      exceeded.  dest_dir is untouched when this is raised.
    """
    # Read caps from Settings if not explicitly overridden
    try:
        from app.config import settings as _s  # noqa: PLC0415

        _max_unc_mb = max_uncompressed_mb or getattr(
            _s, "ZIP_MAX_UNCOMPRESSED_MB", _DEFAULT_MAX_UNCOMPRESSED_MB
        )
        _max_files = max_files or getattr(_s, "ZIP_MAX_FILES", _DEFAULT_MAX_FILES)
    except Exception:  # noqa: BLE001
        _max_unc_mb = max_uncompressed_mb or _DEFAULT_MAX_UNCOMPRESSED_MB
        _max_files = max_files or _DEFAULT_MAX_FILES

    _max_unc_bytes = _max_unc_mb * 1024 * 1024
    _per_entry_bytes = _PER_ENTRY_MAX_MB * 1024 * 1024

    # ------------------------------------------------------------------
    # Open the archive
    # ------------------------------------------------------------------
    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError(f"Cannot open ZIP '{zip_path.name}': {exc}") from exc

    result = ExtractResult()

    with zf:
        # ------------------------------------------------------------------
        # Pre-scan: filter entries and enforce caps before touching dest_dir
        # ------------------------------------------------------------------
        all_infos = zf.infolist()

        # Step 1 — filter out directory entries, junk, and zip-slip
        valid: list[zipfile.ZipInfo] = []
        for info in all_infos:
            name = info.filename
            # Skip directory entries
            if name.endswith("/") or info.is_dir():
                continue
            if _is_junk(name):
                result.skipped.append(name)
                continue
            safe = _safe_dest_rel(name, dest_dir)
            if safe is None:
                log.warning("extract_zip: zip-slip/absolute rejected: %s", name)
                result.skipped.append(name)
                continue
            valid.append(info)

        # Step 2 — file-count cap
        if len(valid) > _max_files:
            raise ArchiveError(
                f"ZIP contains {len(valid)} files, exceeding the cap of {_max_files}."
            )

        # Step 3 — size caps and bomb-ratio check
        total_unc = sum(i.file_size for i in valid)
        total_cmp = sum(i.compress_size for i in valid)

        if total_unc > _max_unc_bytes:
            raise ArchiveError(
                f"ZIP total uncompressed size {total_unc // (1024 * 1024)} MB "
                f"exceeds cap of {_max_unc_mb} MB."
            )
        if total_cmp > 0 and total_unc / total_cmp > _BOMB_RATIO:
            raise ArchiveError(
                f"ZIP compression ratio {total_unc / total_cmp:.0f}× "
                f"exceeds zip-bomb threshold of {_BOMB_RATIO}×."
            )

        # Step 4 — detect lone wrapper prefix and plan dest paths
        effective_names = [info.filename.replace("\\", "/") for info in valid]
        prefix = _lone_wrapper_prefix(effective_names)

        used: set[str] = set(existing_paths or [])
        # plan: list of (ZipInfo, dest_rel_path)
        plan: list[tuple[zipfile.ZipInfo, str]] = []

        for info in valid:
            rel = info.filename.replace("\\", "/")

            # Strip lone wrapper prefix
            if prefix is not None:
                parts = Path(rel).parts
                if parts and parts[0] == prefix:
                    tail_parts = parts[1:]
                    if not tail_parts:
                        result.skipped.append(info.filename)
                        continue
                    rel = str(Path(*tail_parts))
                else:
                    # Entry not under the expected prefix — keep as-is
                    pass

            # Re-validate after stripping (prefix strip can never introduce zip-slip
            # on well-formed ZIPs, but check defensively)
            if _safe_dest_rel(rel, dest_dir) is None:
                result.skipped.append(info.filename)
                continue

            # Collision rename (within archive + against existing_paths)
            rel = _collision_rename(rel, used)
            used.add(rel)
            plan.append((info, rel))

        # ------------------------------------------------------------------
        # Extraction: write every entry into a temp dir under a running byte
        # budget, then — only once all entries are within budget — move them
        # into dest_dir. Writing to the temp dir first (rather than moving each
        # entry as it is written) guarantees dest_dir stays untouched if the
        # runtime budget aborts mid-archive.
        # ------------------------------------------------------------------
        tmp_dir = Path(
            tempfile.mkdtemp(dir=dest_dir.parent, prefix=".pf3d_extract_")
        )
        try:
            # (tmp_dest, dest_rel) for each entry written within budget
            written: list[tuple[Path, str]] = []
            total_written = 0

            for info, dest_rel in plan:
                # Per-entry size sanity cap (declared size from central directory)
                if info.file_size > _per_entry_bytes:
                    result.skipped.append(
                        f"{info.filename} (over per-entry cap: "
                        f"{info.file_size // (1024 * 1024)} MB)"
                    )
                    continue

                tmp_dest = tmp_dir / dest_rel
                tmp_dest.parent.mkdir(parents=True, exist_ok=True)

                try:
                    with zf.open(info) as src, tmp_dest.open("wb") as dst:
                        entry_bytes = _copy_within_budget(
                            src,
                            dst,
                            _per_entry_bytes,
                            _max_unc_bytes - total_written,
                        )
                except _CapExceeded as ce:
                    # Real decompressed bytes blew a cap — abort the whole
                    # extraction. The finally below wipes the temp dir; nothing
                    # has been moved into dest_dir yet, so it stays untouched.
                    log.warning(
                        "extract_zip: %s aborted on %s: %s",
                        zip_path.name,
                        info.filename,
                        ce,
                    )
                    raise ArchiveError(
                        f"ZIP '{zip_path.name}' {ce}."
                    ) from ce
                except Exception as exc:
                    result.errors.append(f"{info.filename}: {exc}")
                    log.warning(
                        "extract_zip: error extracting %s: %s", info.filename, exc
                    )
                    # Clean up the partial file
                    try:
                        tmp_dest.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue

                total_written += entry_bytes
                written.append((tmp_dest, dest_rel))

            # All entries decompressed within budget — commit to dest_dir.
            for tmp_dest, dest_rel in written:
                final = dest_dir / dest_rel
                final.parent.mkdir(parents=True, exist_ok=True)
                try:
                    tmp_dest.replace(final)
                except OSError:
                    # Cross-device fallback
                    shutil.copy2(str(tmp_dest), str(final))
                    tmp_dest.unlink(missing_ok=True)

                result.extracted.append(dest_rel)

        finally:
            # Always clean up the temp dir (removes any files not yet moved)
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

    log.info(
        "extract_zip: %s → extracted=%d skipped=%d errors=%d",
        zip_path.name,
        len(result.extracted),
        len(result.skipped),
        len(result.errors),
    )
    return result
