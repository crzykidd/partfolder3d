"""PartFolder 3D — FastAPI application entry point.

Phase 0: skeleton with /health and /api/version.
CORS, OpenAPI, and the async DB engine are wired up here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .version import __version__

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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
