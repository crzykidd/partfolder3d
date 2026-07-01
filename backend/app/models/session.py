"""Server-side session model.

Sessions are opaque tokens stored in the DB.  The token is delivered to the
browser as an httpOnly cookie; the DB row is the authoritative state.

Decision: DB-backed sessions (vs Redis) — keeps session management in a single
store (Postgres), avoids adding a Redis session-specific code path in Phase 1.
Redis is still used for the job queue (arq) but not for session state.
See docs/decisions.md for the full rationale.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# Session lifetime: 30 days (enforced on creation; checked on every request).
SESSION_LIFETIME_DAYS = 30


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Opaque random token (256 bits of entropy, URL-safe base64).
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Invalidated immediately on logout; also checked against expires_at.
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    # CSRF double-submit token (readable cookie, echoed in X-CSRF-Token header).
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="sessions")  # noqa: F821
