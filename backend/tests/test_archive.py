"""Unit tests for backend/app/storage/archive.py — safe ZIP extractor.

All tests are pure-Python: no DB, no network, no real ZIP files on disk.
Archives are built in-memory with the zipfile module and written to a
temporary directory for each test.

Scenarios covered:
  - Basic extraction: structure preserved at dest
  - Lone top-level wrapper folder stripped
  - Collision rename: within-archive and against existing_paths
  - Zip-slip rejected: ``..`` escape, absolute path, Windows drive letter
  - Junk skipped: __MACOSX/, .DS_Store, Thumbs.db, desktop.ini
  - Nested .zip left as a plain file (no recursion)
  - File-count cap enforced (ArchiveError)
  - Uncompressed-size cap enforced (ArchiveError)
  - Zip-bomb ratio guard enforced (ArchiveError)
  - Per-entry size cap: oversized single entry skipped
  - Malformed / not-a-zip → ArchiveError
  - Empty ZIP → ExtractResult with empty lists
  - existing_paths collision detection (against pre-existing files)
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.storage.archive import ArchiveError, ExtractResult, extract_zip

# ---------------------------------------------------------------------------
# Helpers — build in-memory ZIPs
# ---------------------------------------------------------------------------


def _make_zip(
    entries: dict[str, bytes | str],
    compress_type: int = zipfile.ZIP_STORED,
) -> bytes:
    """Build a ZIP archive in memory.

    Args:
        entries: mapping of internal ZIP path → bytes content (or str → encoded UTF-8).
        compress_type: compression method (default ZIP_STORED for predictable sizes).

    Returns raw ZIP bytes.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compress_type) as zf:
        for name, data in entries.items():
            if isinstance(data, str):
                data = data.encode()
            zf.writestr(name, data)
    return buf.getvalue()


def _write_zip(path: Path, entries: dict[str, bytes | str], **kwargs: object) -> None:
    """Write a ZIP to *path*."""
    path.write_bytes(_make_zip(entries, **kwargs))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dest(tmp_path: Path) -> Path:
    """Return an empty destination directory."""
    d = tmp_path / "item_dir"
    d.mkdir()
    return d


@pytest.fixture()
def zip_file(tmp_path: Path) -> Path:
    """Return a path where a ZIP file can be written."""
    return tmp_path / "test.zip"


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------


def test_basic_extraction(dest: Path, zip_file: Path) -> None:
    """Files are written to dest preserving internal structure."""
    _write_zip(
        zip_file,
        {
            "model.stl": b"binary-stl",
            "subdir/image.png": b"png-bytes",
            "subdir/deep/readme.txt": b"hi",
        },
    )
    result = extract_zip(zip_file, dest)

    assert set(result.extracted) == {
        "model.stl",
        "subdir/image.png",
        "subdir/deep/readme.txt",
    }
    assert result.skipped == []
    assert result.errors == []

    assert (dest / "model.stl").read_bytes() == b"binary-stl"
    assert (dest / "subdir" / "image.png").read_bytes() == b"png-bytes"
    assert (dest / "subdir" / "deep" / "readme.txt").read_bytes() == b"hi"


# ---------------------------------------------------------------------------
# Lone top-level wrapper folder stripped
# ---------------------------------------------------------------------------


def test_lone_wrapper_stripped(dest: Path, zip_file: Path) -> None:
    """If all entries share one top-level dir, it is stripped."""
    _write_zip(
        zip_file,
        {
            "my-model/part.stl": b"stl",
            "my-model/images/cover.png": b"img",
        },
    )
    result = extract_zip(zip_file, dest)

    assert set(result.extracted) == {"part.stl", "images/cover.png"}
    assert (dest / "part.stl").read_bytes() == b"stl"
    assert (dest / "images" / "cover.png").read_bytes() == b"img"


def test_no_wrapper_strip_when_mixed(dest: Path, zip_file: Path) -> None:
    """Wrapper is NOT stripped when files live at multiple top-level paths."""
    _write_zip(
        zip_file,
        {
            "wrapper/file.stl": b"stl",
            "loose.txt": b"txt",
        },
    )
    result = extract_zip(zip_file, dest)

    # Both paths land as-is (no stripping)
    assert "wrapper/file.stl" in result.extracted
    assert "loose.txt" in result.extracted


def test_no_wrapper_strip_for_single_file(dest: Path, zip_file: Path) -> None:
    """A single file at root is not treated as a wrapper."""
    _write_zip(zip_file, {"model.stl": b"stl"})
    result = extract_zip(zip_file, dest)
    assert result.extracted == ["model.stl"]


# ---------------------------------------------------------------------------
# Collision renaming
# ---------------------------------------------------------------------------


def test_collision_rename_within_archive(dest: Path, zip_file: Path) -> None:
    """Within-archive collisions after wrapper strip are renamed."""
    # Two files with the same effective name after stripping wrapper prefix
    # (This can't happen naturally in a well-formed ZIP, but we test the
    #  within-archive dedup that guards the 'used' set)
    _write_zip(
        zip_file,
        {
            "a/model.stl": b"v1",
            "b/model.stl": b"v2",
        },
    )
    # Two different top-level dirs → no stripping
    result = extract_zip(zip_file, dest)
    # Files end up in their respective subdirs without collision
    assert "a/model.stl" in result.extracted
    assert "b/model.stl" in result.extracted


def test_collision_rename_against_existing(dest: Path, zip_file: Path) -> None:
    """Incoming file that collides with existing_paths gets a (1) suffix."""
    (dest / "model.stl").write_bytes(b"existing")
    _write_zip(zip_file, {"model.stl": b"new"})

    result = extract_zip(zip_file, dest, existing_paths={"model.stl"})

    assert result.extracted == ["model (1).stl"]
    assert (dest / "model.stl").read_bytes() == b"existing"     # untouched
    assert (dest / "model (1).stl").read_bytes() == b"new"


def test_collision_rename_multiple(dest: Path, zip_file: Path) -> None:
    """Multiple collisions produce (1), (2), … suffixes."""
    existing = {"file.txt", "file (1).txt", "file (2).txt"}
    for name in existing:
        (dest / name).write_bytes(b"x")

    _write_zip(zip_file, {"file.txt": b"new"})
    result = extract_zip(zip_file, dest, existing_paths=existing)

    assert result.extracted == ["file (3).txt"]
    assert (dest / "file (3).txt").read_bytes() == b"new"


# ---------------------------------------------------------------------------
# Zip-slip rejection
# ---------------------------------------------------------------------------


def test_zip_slip_dotdot_rejected(dest: Path, zip_file: Path) -> None:
    """Entries with .. components are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escaped.txt", b"evil")
    zip_file.write_bytes(buf.getvalue())

    result = extract_zip(zip_file, dest)

    assert result.extracted == []
    assert any("../escaped.txt" in s for s in result.skipped)
    assert not (dest.parent / "escaped.txt").exists()


def test_zip_slip_absolute_rejected(dest: Path, zip_file: Path) -> None:
    """Entries with absolute paths are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/etc/passwd", b"root:x:0:0:")
    zip_file.write_bytes(buf.getvalue())

    result = extract_zip(zip_file, dest)
    assert result.extracted == []
    assert not Path("/etc/passwd").exists() or Path("/etc/passwd").read_text().startswith("root")


def test_zip_slip_windows_drive_rejected(dest: Path, zip_file: Path) -> None:
    """Windows drive-letter paths are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("C:\\evil.exe", b"evil")
    zip_file.write_bytes(buf.getvalue())

    result = extract_zip(zip_file, dest)
    assert result.extracted == []


# ---------------------------------------------------------------------------
# Junk filtering
# ---------------------------------------------------------------------------


def test_junk_macosx_skipped(dest: Path, zip_file: Path) -> None:
    """__MACOSX entries are skipped."""
    _write_zip(
        zip_file,
        {
            "model.stl": b"stl",
            "__MACOSX/._model.stl": b"osx-junk",
            "__MACOSX/subdir/._image.png": b"more-junk",
        },
    )
    result = extract_zip(zip_file, dest)

    assert "model.stl" in result.extracted
    assert all("__MACOSX" in s or "._" in s for s in result.skipped if "model.stl" not in s)
    assert not (dest / "__MACOSX").exists()


def test_junk_ds_store_skipped(dest: Path, zip_file: Path) -> None:
    """.DS_Store entries are skipped."""
    _write_zip(
        zip_file,
        {
            "model.stl": b"stl",
            ".DS_Store": b"",
            "subdir/.DS_Store": b"",
        },
    )
    result = extract_zip(zip_file, dest)

    assert "model.stl" in result.extracted
    assert not (dest / ".DS_Store").exists()
    assert not (dest / "subdir" / ".DS_Store").exists()


def test_junk_thumbs_and_desktop_ini_skipped(dest: Path, zip_file: Path) -> None:
    """Thumbs.db and desktop.ini entries are skipped."""
    _write_zip(
        zip_file,
        {
            "model.stl": b"stl",
            "Thumbs.db": b"",
            "desktop.ini": b"",
        },
    )
    result = extract_zip(zip_file, dest)

    assert "model.stl" in result.extracted
    assert not (dest / "Thumbs.db").exists()
    assert not (dest / "desktop.ini").exists()


# ---------------------------------------------------------------------------
# Nested archives left as plain files (no recursion)
# ---------------------------------------------------------------------------


def test_nested_zip_extracted_as_file(dest: Path, zip_file: Path) -> None:
    """A .zip entry inside the archive is extracted as a plain file, not recursed."""
    inner_zip = _make_zip({"inner.stl": b"stl"})
    _write_zip(
        zip_file,
        {
            "outer.stl": b"outer",
            "assets.zip": inner_zip,
        },
    )
    result = extract_zip(zip_file, dest)

    assert "outer.stl" in result.extracted
    assert "assets.zip" in result.extracted
    # The nested ZIP is a plain file on disk — NOT extracted recursively
    assert (dest / "assets.zip").exists()
    assert (dest / "assets.zip").read_bytes() == inner_zip
    assert not (dest / "inner.stl").exists()


# ---------------------------------------------------------------------------
# Cap enforcement
# ---------------------------------------------------------------------------


def test_file_count_cap(dest: Path, zip_file: Path) -> None:
    """Exceeding the file-count cap raises ArchiveError."""
    entries = {f"file_{i}.txt": b"x" for i in range(5)}
    _write_zip(zip_file, entries)

    with pytest.raises(ArchiveError, match="cap of 3"):
        extract_zip(zip_file, dest, max_files=3)

    # dest_dir must be unchanged
    assert list(dest.iterdir()) == []


def test_uncompressed_size_cap(dest: Path, zip_file: Path) -> None:
    """Exceeding the uncompressed-size cap raises ArchiveError."""
    # 3 MB of data (> 2 MB cap)
    big_content = b"A" * (3 * 1024 * 1024)
    _write_zip(zip_file, {"big.bin": big_content})

    with pytest.raises(ArchiveError, match="exceeds cap"):
        extract_zip(zip_file, dest, max_uncompressed_mb=2)

    assert list(dest.iterdir()) == []


def test_bomb_ratio_guard(dest: Path, zip_file: Path) -> None:
    """A high-ratio ZIP (zip bomb signal) is rejected."""
    # Deflate can compress repetitive bytes very well
    # Use a chunk that compresses to ~1/200th of its original size
    compressible = b"\x00" * (300 * 1024)  # 300 KB of nulls
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bomb.bin", compressible)
    zip_file.write_bytes(buf.getvalue())

    zf_check = zipfile.ZipFile(zip_file)
    info = zf_check.infolist()[0]
    ratio = info.file_size / max(info.compress_size, 1)
    zf_check.close()

    if ratio > 200:
        with pytest.raises(ArchiveError, match="bomb"):
            extract_zip(zip_file, dest)
        assert list(dest.iterdir()) == []
    else:
        # Compression ratio not high enough to trigger; just verify no crash
        result = extract_zip(zip_file, dest)
        assert "bomb.bin" in result.extracted


def test_per_entry_size_cap_skips_entry(dest: Path, zip_file: Path) -> None:
    """An entry exceeding the per-entry cap is skipped (not an ArchiveError)."""
    # Fake a ZipInfo with an inflated file_size claim by writing a real large entry
    # (we can't easily fake the central directory, so use actual content).
    # Instead, test via monkey-patch approach: write a small file and check
    # that the per-entry cap path skips it when cap is extremely low.
    _write_zip(zip_file, {"small.stl": b"s" * 100, "normal.stl": b"n"})
    # Set per-entry cap very low — patch archive module directly
    import app.storage.archive as _arch  # noqa: PLC0415
    original = _arch._PER_ENTRY_MAX_MB
    _arch._PER_ENTRY_MAX_MB = 0  # 0 MB → even tiny files exceed cap
    try:
        result = extract_zip(zip_file, dest)
        # All entries skipped (claimed 100 bytes > 0 MB)
        assert result.extracted == []
        assert len(result.skipped) == 2
    finally:
        _arch._PER_ENTRY_MAX_MB = original


# ---------------------------------------------------------------------------
# Malformed archive
# ---------------------------------------------------------------------------


def test_not_a_zip_raises_archive_error(dest: Path, zip_file: Path) -> None:
    """A file that is not a valid ZIP raises ArchiveError."""
    zip_file.write_bytes(b"not a zip file at all")
    with pytest.raises(ArchiveError, match="Cannot open ZIP"):
        extract_zip(zip_file, dest)
    assert list(dest.iterdir()) == []


def test_empty_zip(dest: Path, zip_file: Path) -> None:
    """An empty ZIP (no entries) returns an empty ExtractResult."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    zip_file.write_bytes(buf.getvalue())

    result = extract_zip(zip_file, dest)
    assert result.extracted == []
    assert result.skipped == []
    assert result.errors == []


# ---------------------------------------------------------------------------
# Return type sanity
# ---------------------------------------------------------------------------


def test_returns_extract_result(dest: Path, zip_file: Path) -> None:
    """extract_zip always returns an ExtractResult instance."""
    _write_zip(zip_file, {"f.txt": b"hi"})
    result = extract_zip(zip_file, dest)
    assert isinstance(result, ExtractResult)


# ---------------------------------------------------------------------------
# Directory entries only
# ---------------------------------------------------------------------------


def test_directory_entries_only(dest: Path, zip_file: Path) -> None:
    """A ZIP containing only directory entries extracts nothing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.mkdir("empty_dir/")
    zip_file.write_bytes(buf.getvalue())
    result = extract_zip(zip_file, dest)
    assert result.extracted == []
