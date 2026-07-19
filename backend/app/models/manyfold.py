"""ManyfoldInstance — admin-configured Manyfold connector instances (Part 1 of 3).

Manyfold is a self-hosted 3D-model organizer with an OAuth2 (client_credentials)
API. An admin registers one or more Manyfold instances by domain, pasting an
OAuth client ID + client secret. Later parts (Part 2: connector/worker/download,
Part 3: frontend) use these credentials to import a model straight from a
Manyfold URL.

``base_url`` is the full origin used for API calls (e.g.
``https://manyfold.crzynet.com``). ``domain`` is the host-only form (e.g.
``manyfold.crzynet.com``), derived from ``base_url`` and kept unique so Part 2
can match an import URL's domain to the right instance.

``client_secret_enc`` is Fernet-encrypted (via ``app.crypto``) — never stored
in plaintext, never returned by the API. See docs/decisions.md.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ManyfoldInstance(Base):
    __tablename__ = "manyfold_instances"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Full origin used for API calls, e.g. "https://manyfold.crzynet.com".
    # Normalized on write: trailing slash stripped, host lowercased,
    # scheme restricted to http/https.
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)

    # Host-only form, e.g. "manyfold.crzynet.com". Derived from base_url.
    # Unique — Part 2 matches an import URL's domain against this column.
    domain: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )

    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # OAuth client_credentials identifier — not a secret, stored plaintext.
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Fernet-encrypted OAuth client secret. Nullable so a row can exist
    # pre-secret (e.g. mid-setup), but the admin router requires it on create.
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # OAuth scope string requested on token fetch. "public" alone runs
    # anonymous; "read" is needed to see owner-private models.
    scopes: Mapped[str] = mapped_column(
        String(255), nullable=False, default="public read"
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Set on a successful POST /{id}/test-connection call.
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
        return f"<ManyfoldInstance id={self.id} domain={self.domain!r}>"
