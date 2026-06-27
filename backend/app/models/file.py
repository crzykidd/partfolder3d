"""File model — a single file that belongs to an Item.

`path` is relative to the item directory.  `role` is inferred from the file's
location/extension at inventory time.  `sha256` is recomputed on change
(cheap-first drift: skip if size + mtime match).
"""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class FileRole(str, enum.Enum):
    model = "model"
    zip = "zip"
    image = "image"
    render = "render"
    gcode = "gcode"
    photo = "photo"
    other = "other"


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Path relative to the item directory.
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    role: Mapped[FileRole] = mapped_column(
        Enum(FileRole, name="filerole"), nullable=False
    )
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # SHA-256 hex digest (lowercase); nullable until hashed.
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mtime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Snapshot of size/mtime used for the cheap-first drift check.
    # When both match, skip re-hashing on scan.
    last_seen_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_seen_mtime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    item: Mapped["Item"] = relationship(  # noqa: F821
        "Item", back_populates="files", foreign_keys=[item_id]
    )

    def __repr__(self) -> str:
        return f"<File id={self.id} path={self.path!r} role={self.role}>"
