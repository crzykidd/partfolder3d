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
Phase 9: admin — backup (DB + config, retention), catalog JSON export, reindex
         trigger, tag admin (aliases/categories/merge/approve), site-capabilities
         CRUD, full REST API parity check.
Phase 13: AI usage tracking — record token counts per call, 24h/7d/30d usage
          summary with estimated cost in the admin UI.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

    # Auto-create inbox dir so the scanner works out of the box.
    # Best-effort: log on failure, never crash startup.
    try:
        inbox = Path(settings.INBOX_DIR)
        inbox.mkdir(parents=True, exist_ok=True)
        log.debug("Startup: ensured inbox dir %s", inbox)
    except Exception:
        log.warning(
            "Startup: could not create inbox dir %s (non-fatal)", settings.INBOX_DIR
        )

    # One shared arq Redis pool for the whole process, injected via get_arq_pool.
    # Replaces the old per-request create_pool/aclose pattern (leaked on error).
    from .worker.arq_pool import create_arq_pool  # noqa: PLC0415

    app.state.arq_pool = await create_arq_pool()
    log.info("Startup: arq Redis pool created")

    try:
        yield
    finally:
        pool = getattr(app.state, "arq_pool", None)
        if pool is not None:
            await pool.aclose()
            log.info("Shutdown: arq Redis pool closed")


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
# Global catch-all exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return a generic 500 for any *unhandled* exception; log the real cause.

    Why this is safe re: HTTPException / RequestValidationError — Starlette
    installs a bare ``Exception`` handler on the OUTER ``ServerErrorMiddleware``,
    while ``HTTPException`` and ``RequestValidationError`` are handled first by
    the INNER ``ExceptionMiddleware`` (via their own dedicated handlers) and
    return their response before it can propagate outward. So this handler only
    ever sees genuinely unhandled errors — well-formed 4xx responses keep their
    status and detail untouched, and never reach here.

    The full traceback goes to the server log (``log.exception``); the client
    gets a fixed generic body so no internal exception text / stack detail can
    leak into the HTTP response (which FastAPI's default handler can do when
    debug mode is on).

    CORS note: like FastAPI's built-in 500 handler, this runs in the outer
    ``ServerErrorMiddleware`` (outside ``CORSMiddleware``), so 500 bodies carry
    no CORS headers — identical to the prior default behavior; nothing regresses.
    Well-formed HTTPException responses still pass back through CORSMiddleware.
    """
    log.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from .routers import (  # noqa: E402  # noqa: E402
    agentql,
    ai_actions,
    ai_providers,
    ai_usage,
    api_keys,
    auth,
    backup,
    changes,
    creators,
    downloads,
    export,
    fs_browse,
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
    site_capabilities,
    tag_admin,
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
# Phase 13
app.include_router(ai_usage.router)
# Phase 9
app.include_router(backup.router)
app.include_router(export.router)
app.include_router(site_capabilities.router)
app.include_router(tag_admin.router)
# Phase 18 — AgentQL fallback scraper
app.include_router(agentql.router)
# Issue #8 — Admin filesystem browser
app.include_router(fs_browse.router)


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
