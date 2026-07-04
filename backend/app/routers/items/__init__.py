"""Items router package.

Split out of the former monolithic ``routers/items.py`` (audit §D) into cohesive
submodules, mirroring the ``routers/import_sessions/`` precedent:

  schemas.py  — Pydantic request/response models
  helpers.py  — shared pure helpers (_build_item_detail, _sort_clause, …)
  core.py     — item CRUD + listing + rescan + default-image + modified-override + jobs
  images.py   — image upload / delete
  files.py    — file upload / delete / rename

Each submodule owns an ``APIRouter(prefix="/api/items", tags=["items"])``; this
package combines them onto one router so ``main.py``'s existing
``from app.routers import items`` / ``include_router(items.router)`` keeps working
unchanged with identical paths.

``_effective_is_modified`` is re-exported for backward compatibility:
``routers/shares.py`` and ``tests/test_phase15_local_modified.py`` import it as
``from app.routers.items import _effective_is_modified``.
"""

from __future__ import annotations

from fastapi import APIRouter

from .core import router as _core_router
from .files import router as _files_router
from .helpers import _effective_is_modified  # noqa: F401 (re-exported for shares.py + tests)
from .images import router as _images_router
from .move import router as _move_router

# Combined router.  The move router is included first so the literal bulk path
# ``POST /api/items/move`` is registered ahead of any ``/{key}`` patterns.
router = APIRouter()
router.include_router(_move_router)
router.include_router(_core_router)
router.include_router(_images_router)
router.include_router(_files_router)
