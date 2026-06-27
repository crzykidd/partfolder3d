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


settings = Settings()
