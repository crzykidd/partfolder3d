"""ShareAuditEvent — one entry per auditable share-link event.

Event types:
  created            — link was minted (recorded at mint time)
  accessed_view      — public endpoint returned item/catalog data
  accessed_download  — public endpoint returned a file or ZIP
  expired            — link's expiry passed (recorded lazily on next access attempt)
  revoked            — link was revoked by an admin/owner

Records IP address and User-Agent where available (from the HTTP request).
Admin-reviewable via GET /api/shares/{id}/audit.

Note: this table uses BIGSERIAL (BigInteger) PK because access events can be
high-volume on publicly shared links.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ShareAuditEvent(Base):
    __tablename__ = "share_audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    share_link_id: Mapped[int] = mapped_column(
        ForeignKey("share_links.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "created" | "accessed_view" | "accessed_download" | "expired" | "revoked"
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Request context (nullable — not always available, e.g. for created/revoked events)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationship
    share_link: Mapped["ShareLink"] = relationship(  # noqa: F821
        "ShareLink", back_populates="audit_events"
    )

    def __repr__(self) -> str:
        return (
            f"<ShareAuditEvent id={self.id} link={self.share_link_id} "
            f"type={self.event_type!r}>"
        )
