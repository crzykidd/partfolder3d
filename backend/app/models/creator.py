"""Creator model — designer/author of a 3D asset.

Optional and best-effort on an Item.  May be scraped from a source URL, entered
manually, or bound to a local User when that user marks an item as self-designed.
Deduplicatable/mergeable across sites (like Tag).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Creator(Base):
    __tablename__ = "creators"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    profile_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional link to a local User — set only when the user marks an item as
    # their own design. NOT auto-bound on import from another instance (portable).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Back-ref to items (avoid eager-loading the entire item list)
    items: Mapped[list["Item"]] = relationship(  # noqa: F821
        "Item", back_populates="creator", foreign_keys="Item.creator_id"
    )

    def __repr__(self) -> str:
        return f"<Creator id={self.id} name={self.name!r}>"
