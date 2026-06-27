"""Tag, TagAlias, and ItemTag models.

Tags are flat canonical names with optional category/namespace.  Aliases map
source-site or AI-suggested strings onto canonical Tags (Phase 5 reconciliation).
ItemTag is the many-to-many association between Items and Tags.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TagStatus(str, enum.Enum):
    active = "active"
    pending = "pending"


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    popularity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[TagStatus] = mapped_column(
        Enum(TagStatus, name="tagstatus"),
        nullable=False,
        default=TagStatus.active,
    )
    # FK to User who created this tag (nullable: system-created or orphaned)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    aliases: Mapped[list["TagAlias"]] = relationship(
        "TagAlias", back_populates="tag", cascade="all, delete-orphan"
    )
    item_tags: Mapped[list["ItemTag"]] = relationship(
        "ItemTag", back_populates="tag", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name={self.name!r} status={self.status}>"


class TagAlias(Base):
    __tablename__ = "tag_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True
    )

    tag: Mapped["Tag"] = relationship("Tag", back_populates="aliases")

    def __repr__(self) -> str:
        return f"<TagAlias alias={self.alias!r} → tag_id={self.tag_id}>"


class ItemTag(Base):
    __tablename__ = "item_tags"
    __table_args__ = (UniqueConstraint("item_id", "tag_id", name="uq_item_tags"),)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    item: Mapped["Item"] = relationship(  # noqa: F821
        "Item", back_populates="item_tags"
    )
    tag: Mapped["Tag"] = relationship("Tag", back_populates="item_tags")
