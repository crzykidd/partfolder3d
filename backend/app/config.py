"""Application settings — loaded once at startup via Pydantic BaseSettings.

Values are read from environment variables (or a .env file if present).
See .env.example for documentation of every variable.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    ALLOWED_ORIGINS: list[str] = ["http://localhost:8973", "http://localhost:5173"]

    # ---- Session cookies ----
    # Set to False for local http:// dev (Docker or plain uvicorn).
    # MUST be True in production (https only).
    # See docs/decisions.md for the cookie-Secure toggle decision.
    COOKIE_SECURE: bool = True

    # ---- Debug ----
    DEBUG: bool = False

    # ---- Rendering (Phase 4) ----
    # Square resolution for mesh thumbnail PNGs (pixels per side).
    RENDER_RESOLUTION: int = 512
    # Rendering backend: "auto" tries EGL → OSMesa → VTK in order.
    # Override with "egl", "osmesa", or "vtk" to force a specific backend.
    RENDER_BACKEND: str = "auto"
    # Wall-clock kill timeout (seconds) for a single file's render subprocess.
    # The child process is SIGTERM'd (then SIGKILL'd) after this many seconds.
    RENDER_TIMEOUT_S: int = 300
    # Thread cap passed to the render subprocess via numeric-thread env vars
    # (OMP_NUM_THREADS, LP_NUM_THREADS, etc.).  Limits CPU saturation on
    # multi-core hosts; 2 is safe for a shared server.
    RENDER_CPU_THREADS: int = 2
    # Background-render mode — controls when items are auto-rendered:
    #   "all"       → render every mesh item (default).
    #   "no_images" → only render items that have no images (render as a
    #                 fallback thumbnail; skip items that already have images).
    #   "off"       → never auto-render.
    # Unknown values fall back to "all" behaviour.
    RENDER_MODE: str = "all"

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


settings = Settings()
