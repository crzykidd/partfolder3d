"""Item model — a single 3D asset with its metadata, files, and images.

The item's stable on-disk identity is `<slug>-<key>/`; `key` never changes.
`dir_path` is the absolute path to the item directory inside its library mount.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable, never-changing identity (6–8 char base32 lowercase).
    key: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    # slug = sanitized title body + key suffix, matches the dir name and URL.
    slug: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    license: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creator_id: Mapped[int | None] = mapped_column(
        ForeignKey("creators.id", ondelete="SET NULL"), nullable=True
    )
    # Denormalized FK — added after images table; kept nullable so no chicken-and-egg.
    default_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL", use_alter=True, name="fk_items_default_image"),
        nullable=True,
    )
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Absolute path to the item directory inside its library mount.
    dir_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Full-text search vector (title + description + tag names).
    # Maintained application-side; updated whenever title/description/tags change.
    # GIN index added in migration 0004.
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)

    # ---- Phase 15: local-modification tracking ----
    # Snapshot of model-file path→sha256 captured at import commit.
    # Null for items without source_url or created before this feature.
    source_baseline: Mapped[Any] = mapped_column(JSONB, nullable=True)
    # Best-effort version/updated marker from the scraper at import.
    # Reserved for future upstream-update check (type 2). May be null.
    source_version: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Set by the scan engine when current model files diverge from source_baseline.
    locally_modified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Timestamp when divergence was last detected (or cleared).
    locally_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Manual override: 'modified' | 'original' | null.
    # Effective state = override if set, else locally_modified.
    modified_override: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    library: Mapped["Library"] = relationship(  # noqa: F821
        "Library", back_populates="items"
    )
    creator: Mapped["Creator | None"] = relationship(  # noqa: F821
        "Creator", back_populates="items", foreign_keys=[creator_id]
    )
    files: Mapped[list["File"]] = relationship(  # noqa: F821
        "File", back_populates="item", cascade="all, delete-orphan",
        foreign_keys="File.item_id"
    )
    images: Mapped[list["Image"]] = relationship(  # noqa: F821
        "Image", back_populates="item", cascade="all, delete-orphan",
        foreign_keys="Image.item_id",
        primaryjoin="Item.id == Image.item_id",
    )
    default_image: Mapped["Image | None"] = relationship(  # noqa: F821
        "Image",
        foreign_keys=[default_image_id],
        primaryjoin="Item.default_image_id == Image.id",
        post_update=True,
    )
    item_tags: Mapped[list["ItemTag"]] = relationship(  # noqa: F821
        "ItemTag", back_populates="item", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Item id={self.id} key={self.key!r} title={self.title!r}>"
