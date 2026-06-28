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


settings = Settings()
