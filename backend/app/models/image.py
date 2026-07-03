"""Image model — a scraped or uploaded image belonging to an Item.

`path` is relative to the item directory.  `is_default` is denormalized from
Item.default_image_id for easier queries; keep the two in sync on write.
`order` controls the display carousel order.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ImageSource(str, enum.Enum):
    scraped = "scraped"
    uploaded = "uploaded"
    render = "render"
    embedded = "embedded"
    captured = "captured"


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Path relative to the item directory (e.g. "images/cover.png").
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    source: Mapped[ImageSource] = mapped_column(
        Enum(ImageSource, name="imagesource"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    item: Mapped["Item"] = relationship(  # noqa: F821
        "Item",
        back_populates="images",
        foreign_keys=[item_id],
        primaryjoin="Image.item_id == Item.id",
    )

    def __repr__(self) -> str:
        return f"<Image id={self.id} path={self.path!r} source={self.source}>"
