"""Admin-only filesystem folder browser (issue #8).

GET /api/admin/fs/browse?path=<abs>

Returns the immediate child *directories* of the requested path, constrained
to the operator-configured allowlist (FS_BROWSE_ROOTS in settings).

Security model
--------------
1. Admin-only   — 403 for any non-admin caller.
2. Allowlist    — Every requested path must resolve() inside at least one root
                  in settings.FS_BROWSE_ROOTS.  Paths outside all roots are
                  rejected with 400.  The check mirrors the path-traversal
                  barrier in downloads.py.
3. No path      — Returns the configured roots as the top-level entry list;
                  no filesystem listing is performed.
4. Graceful     — Non-existent / non-directory / permission-denied paths get
                  clear 4xx responses; no OS tracebacks are leaked.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..auth.deps import require_admin
from ..config import settings
from ..models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/fs", tags=["admin-fs"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FsBrowseEntry(BaseModel):
    name: str
    abs_path: str


class FsBrowseResult(BaseModel):
    path: str | None
    parent: str | None
    entries: list[FsBrowseEntry]


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def _allowlist_roots() -> list[Path]:
    """Return the configured browse roots as Path objects."""
    return [Path(r) for r in settings.FS_BROWSE_ROOTS]


def _inside_any_root(resolved: Path, roots: list[Path]) -> bool:
    """Return True if *resolved* is the same as or inside any configured root."""
    return any(resolved == root or resolved.is_relative_to(root) for root in roots)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/browse", response_model=FsBrowseResult)
async def browse_directory(
    _admin: Annotated[User, Depends(require_admin)],
    path: str | None = Query(
        default=None,
        description=(
            "Absolute container path to list.  Omit to get the configured "
            "allowlist roots as starting points."
        ),
    ),
) -> FsBrowseResult:
    """List immediate child directories of *path*.

    When *path* is omitted, returns the configured FS_BROWSE_ROOTS so the
    UI can start navigation without exposing arbitrary filesystem structure.

    All paths are validated against the FS_BROWSE_ROOTS allowlist; any path
    that resolves outside all configured roots is rejected with 400.
    """
    roots = _allowlist_roots()

    # ---- No path: return the configured roots --------------------------------
    if path is None:
        entries = [FsBrowseEntry(name=r.name or str(r), abs_path=str(r)) for r in roots]
        return FsBrowseResult(path=None, parent=None, entries=entries)

    # ---- Resolve and containment-check --------------------------------------
    try:
        requested_raw = Path(path)
        # Reject any non-absolute path immediately (avoids weird relative-path tricks)
        if not requested_raw.is_absolute():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="path must be an absolute filesystem path.",
            )
        resolved = requested_raw.resolve()
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path.",
        ) from exc

    if not _inside_any_root(resolved, roots):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is outside the allowed filesystem roots.",
        )

    # ---- Existence / type checks --------------------------------------------
    if not resolved.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Path does not exist.",
        )

    if not resolved.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory.",
        )

    # ---- List child directories ---------------------------------------------
    entries: list[FsBrowseEntry] = []
    try:
        with os.scandir(resolved) as it:
            for entry in sorted(it, key=lambda e: e.name.lower()):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        entries.append(
                            FsBrowseEntry(
                                name=entry.name,
                                abs_path=str(resolved / entry.name),
                            )
                        )
                except OSError:
                    # Skip entries we can't stat (permission denied, etc.)
                    pass
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied reading directory.",
        ) from exc
    except OSError as exc:
        # Strip CR/LF from the (user-influenced) path before logging to avoid
        # log injection — a directory name can technically contain newlines.
        safe_path = str(resolved).replace("\r", "").replace("\n", "")
        log.warning("fs_browse: OS error reading %s: %s", safe_path, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot read directory.",
        ) from exc

    # ---- Compute parent path (only if still inside the allowlist) -----------
    parent: str | None = None
    parent_candidate = resolved.parent
    if parent_candidate != resolved and _inside_any_root(parent_candidate, roots):
        parent = str(parent_candidate)

    return FsBrowseResult(
        path=str(resolved),
        parent=parent,
        entries=entries,
    )
