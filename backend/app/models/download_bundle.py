"""DownloadBundle — lightweight tracking for queued ZIP downloads.

A bundle is created when a user requests a ZIP of an item's directory.
The actual ZIP is built by an arq worker task.  The bundle records:
  - status:          pending | ready | failed | expired
  - bundle_path:     absolute path to the .zip file (set when ready)
  - inventory_hash:  SHA-256 of the file inventory at enqueue time;
                     used to detect staleness (if files change, hash differs
                     and the bundle is invalidated when a new request arrives)
  - expires_at:      ~1 day from creation (PRD §11)

Bundles are NOT purged automatically in Phase 3; a cleanup job arrives in
Phase 9.  Expired bundles are skipped by the API and left on disk until purge.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DownloadBundle(Base):
    __tablename__ = "download_bundles"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # pending → ready (or failed)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Absolute path to the ZIP on disk; set when status transitions to "ready".
    bundle_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Hash of the file inventory at the time the bundle was requested.
    # Used to detect whether the item's files have changed since the ZIP was built.
    inventory_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 7: include print history in ZIP (PRD §11).
    # When True, includes print records in the ZIP.
    # Whether private records are included depends on requester_user_id:
    #   - requester_user_id is set (authenticated user): all records included
    #   - requester_user_id is None (public/anonymous): only public records
    include_print_history: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # The user who requested this bundle (null for public/share-link downloads).
    requester_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DownloadBundle id={self.id} item_id={self.item_id} status={self.status!r}>"
        )
