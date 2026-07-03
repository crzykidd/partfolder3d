"""Application settings — loaded once at startup via Pydantic BaseSettings.

Values are read from environment variables (or a .env file if present).
See .env.example for documentation of every variable.
"""

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---- Database ----
    DATABASE_URL: str = (
        "postgresql+asyncpg://partfolder3d:changeme@localhost:5432/partfolder3d"
    )

    # ---- Redis / job queue ----
    REDIS_URL: str = "redis://localhost:6379"

    # ---- App paths ----
    DATA_DIR: str = "/data"

    # ---- API / CORS ----
    # Accepts the operator-friendly comma-separated form documented in
    # .env.example (ALLOWED_ORIGINS=https://a.example,https://b.example), a JSON
    # array, or empty. NoDecode disables pydantic-settings' JSON-only decoding so
    # a plain comma-separated value no longer raises a SettingsError at boot.
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:8973",
        "http://localhost:5173",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("["):  # explicit JSON array
                import json

                return json.loads(s)
            return [part.strip() for part in s.split(",") if part.strip()]
        return v

    # ---- Session cookies ----
    # Set to False for local http:// dev (Docker or plain uvicorn).
    # MUST be True in production (https only).
    # See docs/decisions.md for the cookie-Secure toggle decision.
    COOKIE_SECURE: bool = True

    # ---- Debug ----
    DEBUG: bool = False

    # ---- Rendering (Phase 4 / render-rework-A) ----
    # Square resolution for mesh thumbnail PNGs (pixels per side).
    RENDER_RESOLUTION: int = 512
    # Rendering backend: "auto" probes VTK offscreen (the only supported backend).
    # Override with "vtk" to make the choice explicit.
    RENDER_BACKEND: str = "auto"
    # Wall-clock kill timeout (seconds) for a single file's render subprocess.
    # The child process is SIGTERM'd (then SIGKILL'd) after this many seconds.
    RENDER_TIMEOUT_S: int = 300
    # Thread cap passed to the render subprocess via numeric-thread env vars
    # (OMP_NUM_THREADS, LP_NUM_THREADS, etc.).  Limits CPU saturation on
    # multi-core hosts; 2 is safe for a shared server.
    RENDER_CPU_THREADS: int = 2
    # Background-render mode — controls when items are auto-rendered:
    #   "all"       → render every eligible mesh item (default).
    #   "no_images" → only render items that have no images (render as a
    #                 fallback thumbnail; skip items that already have images).
    #   "off"       → never auto-render.
    # Unknown values fall back to "all" behaviour.
    RENDER_MODE: str = "all"
    # Max file size (MB) for server-side STL/OBJ/PLY rendering.
    # Files over this cap are skipped silently (no render, no error).
    RENDER_MAX_FILE_MB: int = 50
    # Max triangle count for server-side rendering.
    # Meshes with more triangles are skipped silently after loading.
    RENDER_MAX_TRIANGLES: int = 1_000_000
    # Max file size (MB) for the in-browser 3D preview flag (preview_3d on FileOut).
    # Files over this size get preview_3d=False; the browser viewer is not offered.
    BROWSER_PREVIEW_MAX_MB: int = 50

    # ---- Worker concurrency & resource limits ----
    # How many background jobs the arq worker runs AT ONCE.  Higher = the queue
    # drains faster, but uses more CPU/RAM.  A bulk import floods the queue, so on
    # a small host too high a value will thrash CPU + memory and starve everything
    # else (including the API).  Rule of thumb: ~1 per 2 CPU cores.  Renders and
    # mesh analysis are the heavy jobs — cap them separately below.
    WORKER_MAX_JOBS: int = 2
    # Max 3D RENDER jobs running at once, independent of WORKER_MAX_JOBS.  Renders
    # are the heaviest work (each loads a mesh + runs a vtk-osmesa subprocess using
    # RENDER_CPU_THREADS cores and hundreds of MB of RAM).  Keep at 1 on a host with
    # < ~16 GB RAM — raising this is the quickest way to OOM a small box.
    RENDER_CONCURRENCY: int = 1
    # Max mesh-ANALYSIS jobs running at once.  Analysis loads whole meshes into RAM
    # (trimesh); on a memory-constrained host keep this low (1–2).
    ANALYZE_CONCURRENCY: int = 2

    # ---- Import / Inbox (Phase 5) ----
    # Directory the inbox scanner watches for incoming asset folders.
    # Each direct subdirectory is treated as one pending import.
    INBOX_DIR: str = "/data/inbox"
    # Minimum seconds since a folder's last modification before it is picked up
    # by the scanner (prevents ingesting folders that are still being written).
    INBOX_MTIME_SETTLE_SECONDS: int = 30
    # HTTP timeout (seconds) for URL scrape requests.
    SCRAPE_TIMEOUT: int = 15
    # Maximum number of images to collect per scrape.
    SCRAPE_MAX_IMAGES: int = 20

    # ---- Sharing (Phase 7) ----
    # Default expiry for new share links, in days.
    # Can be overridden per-link.  Set to 0 for "never expires".
    # Also stored as DB setting "share_default_expiry_days" for per-instance override.
    SHARE_DEFAULT_EXPIRY_DAYS: int = 30
    # HTTP timeout (seconds) for instance-to-instance import fetch.
    INSTANCE_IMPORT_TIMEOUT: int = 30

    # ---- Job retention (Phase 19) ----
    # Days after which a succeeded job row is hard-deleted by the daily retention cron.
    JOB_RETENTION_SUCCEEDED_DAYS: int = 7
    # Days after which a failed/cancelled/superseded job row is hard-deleted.
    JOB_RETENTION_FAILED_DAYS: int = 30

    # ---- ZIP auto-extraction (Phase B / render-rework-B) ----
    # Maximum total uncompressed size (MB) of a single ZIP archive.
    # Archives exceeding this cap are rejected with a clear error.
    ZIP_MAX_UNCOMPRESSED_MB: int = 2048
    # Maximum number of files in a single ZIP archive.
    ZIP_MAX_FILES: int = 10_000

    # ---- Admin filesystem browser (issue #8) ----
    # Comma-separated absolute paths (or JSON array) that admins are allowed to
    # browse via GET /api/admin/fs/browse.  Any path resolving outside ALL of
    # these roots is rejected with 400.  Never allow "/" or system paths here.
    FS_BROWSE_ROOTS: Annotated[list[str], NoDecode] = ["/library"]

    @field_validator("FS_BROWSE_ROOTS", mode="before")
    @classmethod
    def _parse_fs_browse_roots(cls, v: object) -> object:
        if v is None:
            return ["/library"]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return ["/library"]
            if s.startswith("["):  # explicit JSON array
                import json

                return json.loads(s)
            return [part.strip() for part in s.split(",") if part.strip()]
        return v


settings = Settings()
