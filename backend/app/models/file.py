"""File model — a single file that belongs to an Item.

`path` is relative to the item directory.  `role` is inferred from the file's
location/extension at inventory time.  `sha256` is recomputed on change
(cheap-first drift: skip if size + mtime match).
"""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
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
    # Design-source file (e.g. OpenSCAD .scad) — not a printable/mesh asset.
    # Named generically so more source formats can be added later without
    # another enum migration.
    source = "source"


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
    # Phase 16: per-object mesh analysis (JSON, sha-keyed; null until analyzed)
    object_analysis: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    # Issue #46: marks this File as a machine-generated derived asset (e.g. the
    # STL server-compiled from a .scad source) rather than a user-provided
    # original. Non-null generated_from_file_id IS the "is generated" marker —
    # no separate boolean, so there is exactly one source of truth. Points at
    # the source File (e.g. the .scad) this asset was compiled from.
    # ondelete=SET NULL: deleting the source file (or the whole item cascades
    # away first) must not be blocked by — or delete — the derived asset.
    generated_from_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # sha256 of the SOURCE file at the time this asset was generated from it —
    # lets the compile step skip a re-compile when the source hasn't changed
    # since (cheap "is this derived asset stale?" check, same idea as the
    # cheap-first drift check above) without re-running openscad every pass.
    generated_source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    item: Mapped["Item"] = relationship(  # noqa: F821
        "Item", back_populates="files", foreign_keys=[item_id]
    )

    def __repr__(self) -> str:
        return f"<File id={self.id} path={self.path!r} role={self.role}>"
