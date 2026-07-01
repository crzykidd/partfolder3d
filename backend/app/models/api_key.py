"""Per-user API key model.

Storage strategy (see docs/decisions.md):
  The raw API key is shown to the user once at creation and never stored in
  cleartext.  We store a SHA-256 hash of the key for O(1) lookup/verification.
  A once-only display model (user copies the key at creation; it cannot be
  retrieved later) means encryption would add key-management cost with no benefit
  — you could only redisplay the key to the user, which we explicitly do not do.
  SHA-256 of a 256-bit random token is preimage-resistant and sufficient here.
  This satisfies "never stored in cleartext" from PRD §4; the deviation from
  "encrypted" is documented because hash-only is strictly more restrictive
  (the raw value is irrecoverable even with key access), which is the right
  security posture for once-only-display credentials.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 hex digest of the raw key (used for O(1) lookup).
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Future: JSON array of scope strings (null = full access).
    scopes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    user: Mapped["User"] = relationship("User", back_populates="api_keys")  # noqa: F821
