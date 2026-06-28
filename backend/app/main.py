"""PartFolder 3D — FastAPI application entry point.

Phase 1: identity layer added (encryption key, models, auth, sessions, CSRF,
         invites, password reset, settings, API keys, first-run wizard).
Phase 2: libraries, storage, sidecar, item core added.
Phase 3: catalog UI backend — search, favorites, tag browse, creator browse,
         downloads (single file + queued ZIP), set-default-image, path-prefix.
Phase 4: job monitor + scheduled-jobs API.
Phase 5: import wizard — import sessions, site capabilities, inbox scanner,
         URL scraping, tag reconciliation + pending-tag approval.
Phase 6: reconciliation / scan engine — issues, change log, review items.
Phase 7: print history (PrintRecord + gcode parse + stats) + sharing
         (ShareLink + public endpoints + audit + share-link import).
Phase 8: optional AI assist — provider CRUD, tag suggestions, description
         cleanup, scrape summarization. Manual-only always works with zero AI.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .crypto import ensure_key
from .version import __version__

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: ensure encryption key, recover stale move journals."""
    ensure_key()
    # Recover any stale journal files left by interrupted rename operations.
    # This is safe to call at every startup (idempotent).
    try:
        from .db import SessionLocal  # noqa: PLC0415
        from .storage.journal import recover_stale_journals  # noqa: PLC0415

        async with SessionLocal() as db:
            await recover_stale_journals(db)
    except Exception:
        log.exception("Startup journal recovery failed (non-fatal)")
    yield


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PartFolder 3D",
    description="Self-hosted 3D-printing asset manager",
    version=__version__,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from .routers import (  # noqa: E402  # noqa: E402
    ai_actions,
    ai_providers,
    api_keys,
    auth,
    changes,
    creators,
    downloads,
    import_sessions,
    invites,
    issues,
    items,
    jobs,
    libraries,
    me,
    password_reset,
    print_records,
    reviews,
    setup,
    shares,
    tags,
    users,
)
from .routers import scheduled_jobs as scheduled_jobs_router  # noqa: E402
from .routers import settings as settings_router  # noqa: E402

app.include_router(setup.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(invites.router)
app.include_router(password_reset.router)
app.include_router(settings_router.router)
app.include_router(api_keys.router)
app.include_router(libraries.router)
app.include_router(items.router)
# Phase 3
app.include_router(tags.router)
app.include_router(creators.router)
app.include_router(me.router)
app.include_router(downloads.router)
# Phase 4
app.include_router(jobs.router)
app.include_router(scheduled_jobs_router.router)
# Phase 5
app.include_router(import_sessions.router)
# Phase 6
app.include_router(issues.router)
app.include_router(changes.router)
app.include_router(reviews.router)
# Phase 7
app.include_router(print_records.router)
app.include_router(shares.router)
# Phase 8
app.include_router(ai_providers.router)
app.include_router(ai_actions.router)


# ---------------------------------------------------------------------------
# Health + version routes (available before auth, no DB needed)
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe — returns {"status": "ok"}."""
    return {"status": "ok"}


@app.get("/api/version", tags=["meta"])
async def version() -> dict[str, str]:
    """Return the running application version."""
    return {"version": __version__}
