"""ShareLink — tokenized public read-only link for an item or the full catalog.

Security properties (PRD §10):
  - token:   32 random bytes from secrets.token_hex(32) → 64-char hex string.
             Never reversible to internal IDs.  Stored as-is (not hashed) so
             public endpoints can look up the link in O(1) from the URL alone.
  - scope:   "item_design" (per-design, item_id required) or
             "full_site" (admin-only, item_id null).
  - expiry:  expires_at = None means the link never expires (admin-set).
             A default expiry is configured via DB setting "share_default_expiry_days".
  - revoked: soft-delete; once revoked the link is dead and never re-activatable.
  - Public endpoints check: token exists, not expired, not revoked on EVERY request.
  - Private notes/records NEVER appear through a public link.

Share audit events are in a separate ShareAuditEvent table.
"""

import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _generate_token() -> str:
    """Generate a 64-char hex share token (256 bits of entropy)."""
    return secrets.token_hex(32)


class ShareLink(Base):
    __tablename__ = "share_links"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Unguessable token — 64 hex chars (256-bit).  Used as the URL path component.
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, default=_generate_token
    )

    # Scope: "item_design" | "full_site"
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="item_design")

    # For item_design scope: the item this link exposes.
    # Null for full_site links.
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Who created this link
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Expiry (None = never expires)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Revocation
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Label / description (optional, for admin reference)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    item: Mapped["Item | None"] = relationship("Item")  # noqa: F821
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[created_by_id]
    )
    revoked_by: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[revoked_by_id]
    )
    audit_events: Mapped[list["ShareAuditEvent"]] = relationship(  # noqa: F821
        "ShareAuditEvent", back_populates="share_link", cascade="all, delete-orphan"
    )

    def is_active(self) -> bool:
        """Return True if this link is usable right now."""
        from datetime import UTC

        if self.revoked:
            return False
        if self.expires_at is not None and self.expires_at < datetime.now(UTC):
            return False
        return True

    def __repr__(self) -> str:
        return (
            f"<ShareLink id={self.id} scope={self.scope!r} "
            f"token={self.token[:8]}... revoked={self.revoked}>"
        )
