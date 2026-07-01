"""Utility helpers for the per-library × per-OS path prefix feature.

Split out of migration 0017 so the logic can be tested without importing
the alembic migration module (whose filename starts with a digit).
"""

from __future__ import annotations


def infer_prefix_map(
    path_prefix: str,
    library_ids: list[int],
) -> dict[str, dict[str, str | None]]:
    """Convert a legacy single path_prefix into a per-library prefix map.

    The OS is inferred from the prefix string: a backslash anywhere → windows,
    otherwise posix.  The prefix is applied to every library in library_ids.

    Returns a dict keyed by ``str(library_id)`` whose values are
    ``{"windows": str|None, "posix": str|None}``.
    """
    os_key: str = "windows" if "\\" in path_prefix else "posix"
    other_key: str = "posix" if os_key == "windows" else "windows"
    return {
        str(lib_id): {
            os_key: path_prefix,
            other_key: None,
        }
        for lib_id in library_ids
    }
