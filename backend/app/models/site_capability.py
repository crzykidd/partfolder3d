"""SiteCapability and SiteToken — per-domain scrape capability tracking (Phase 5).

SiteCapability records what is publicly scrape-able for a given domain:
  - can_scrape_metadata: can we fetch title/description/tags/creator without auth?
  - can_scrape_images: can we fetch images without auth?
  - requires_token: files require an API token (stored in SiteToken, encrypted)
  - is_manual_only: user override to skip scraping entirely for this domain

SiteToken stores an encrypted auth token for a domain.  The token is encrypted
using the instance Fernet key (storage/keys.py → crypto.py).

Recorded in docs/decisions.md.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SiteCapability(Base):
    __tablename__ = "site_capabilities"

    # Primary key: the registrable domain (e.g. "thingiverse.com")
    domain: Mapped[str] = mapped_column(String(255), primary_key=True)

    # What can be done without auth
    can_scrape_metadata: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    can_scrape_images: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # Token required to download files (not for metadata)
    requires_token: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # User has explicitly disabled scraping for this domain
    is_manual_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    last_probed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Optional human-readable notes (e.g. "Requires login after N requests")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<SiteCapability domain={self.domain!r} manual_only={self.is_manual_only}>"


class SiteToken(Base):
    """Encrypted auth token for a domain.

    The token value is encrypted with the instance Fernet key before storage.
    Never store plaintext tokens in this table.
    """

    __tablename__ = "site_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    # Fernet-encrypted token (base64url safe; starts with "gAAAAAA..." when encrypted)
    encrypted_token: Mapped[str] = mapped_column(String(4096), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<SiteToken domain={self.domain!r}>"
