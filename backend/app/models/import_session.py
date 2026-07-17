"""ImportSession — staging entity for the Phase 5 import wizard.

An ImportSession lives between "user initiates an import" and "item is committed".
It holds all in-progress state (staged files, scraped/sidecar metadata, tag
reconciliation, creator choice) so the wizard can be interrupted and resumed.

Status flow:
  draft           → created, not yet processed
  processing      → import job is running (scraping / sidecar read / tag reconc.)
  pending_wizard  → processing done; waiting for user to review in the wizard
  committed       → finalized into a real Item (item_id is set)
  failed          → job or commit failed (error is set)
  cancelled       → discarded by user

Source types:
  upload    — user uploaded files via Add Asset
  inbox     — detected by the inbox-scan scheduled job
  url       — source-URL-only (no files uploaded; just a URL to scrape)
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ImportSessionStatus(str, enum.Enum):
    draft = "draft"
    processing = "processing"
    pending_wizard = "pending_wizard"
    committed = "committed"
    failed = "failed"
    cancelled = "cancelled"


class ImportSourceType(str, enum.Enum):
    upload = "upload"
    inbox = "inbox"
    url = "url"


class ImportSession(Base):
    __tablename__ = "import_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[ImportSessionStatus] = mapped_column(
        Enum(ImportSessionStatus, name="importsessionstatus"),
        nullable=False,
        default=ImportSessionStatus.draft,
        index=True,
    )
    source_type: Mapped[ImportSourceType] = mapped_column(
        Enum(ImportSourceType, name="importsourcetype"),
        nullable=False,
    )

    # ---- Source references ----
    # URL to scrape (for source_type=url or as extra info for inbox/upload)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Absolute path to the inbox subfolder (for source_type=inbox)
    inbox_folder: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    # Absolute path to the staging directory (for source_type=upload / inbox copy)
    staging_dir: Mapped[str | None] = mapped_column(String(4096), nullable=True)

    # ---- Pre-filled / user-editable metadata ----
    suggested_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    confirmed_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_site: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ---- Creator ----
    creator_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    creator_profile_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    creator_source_site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # True if user checked "this is my own design"
    creator_is_own_design: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Resolved creator FK (set at commit time)
    creator_id: Mapped[int | None] = mapped_column(
        ForeignKey("creators.id", ondelete="SET NULL"), nullable=True
    )

    # ---- Tag reconciliation state ----
    # JSONB: {"confirmed": ["tag1", "tag2"], "pending": ["unknown-tag"]}
    # confirmed = mapped to canonical/alias tags
    # pending   = new tags queued for approval (TagStatus.pending)
    tag_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ---- Default image ----
    # For inbox/upload: relative path inside staging_dir or inbox_folder.
    # For URL imports: the selected image URL.
    default_image_path: Mapped[str | None] = mapped_column(String(4096), nullable=True)

    # ---- Library to commit into ----
    library_id: Mapped[int | None] = mapped_column(
        ForeignKey("libraries.id", ondelete="SET NULL"), nullable=True
    )

    # ---- Job + result links ----
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )

    # ---- Ownership + timestamps ----
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Annotation set by the worker:
    # • "Fetched via AgentQL" when agentql fallback succeeded.
    # • A blocked/budget reason when static scrape was blocked and agentql unavailable.
    # • None for standard static scrapes.
    scrape_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- Relationships ----
    files: Mapped[list["ImportSessionFile"]] = relationship(
        "ImportSessionFile",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    images: Mapped[list["ImportSessionImage"]] = relationship(
        "ImportSessionImage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ImportSessionImage.order",
    )

    def __repr__(self) -> str:
        return (
            f"<ImportSession id={self.id} status={self.status} "
            f"source={self.source_type}>"
        )


class ImportSessionFile(Base):
    """A staged file associated with an ImportSession."""

    __tablename__ = "import_session_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("import_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Absolute path to the staged/inbox file (not yet moved to library)
    staged_path: Mapped[str] = mapped_column(String(4096), nullable=False)
    # Original filename as provided by the user
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="model")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Whether this staged file should be moved into the item on commit.
    # Defaults True so pre-existing behavior (every staged file lands in the
    # item) is unchanged; a Manyfold model import can stage several files at
    # once and the wizard lets the user deselect ones they don't want.
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    session: Mapped["ImportSession"] = relationship(
        "ImportSession", back_populates="files"
    )

    def __repr__(self) -> str:
        return f"<ImportSessionFile id={self.id} name={self.original_name!r}>"


class ImportSessionImage(Base):
    """A candidate image for an ImportSession.

    For inbox/upload sources: path is a relative-to-staging or absolute path.
    For URL sources: path is the image URL (downloaded at commit time if is_url=True).
    """

    __tablename__ = "import_session_images"
    __table_args__ = (UniqueConstraint("session_id", "order", name="uq_isi_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("import_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # URL or file path
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    is_url: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # "scrape" | "upload" | "sidecar"
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    session: Mapped["ImportSession"] = relationship(
        "ImportSession", back_populates="images"
    )

    def __repr__(self) -> str:
        return f"<ImportSessionImage id={self.id} order={self.order}>"
