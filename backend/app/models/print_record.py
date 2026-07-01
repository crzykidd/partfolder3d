"""PrintRecord — log of a single print attempt for an item.

Fields:
  note            free-text note (private or public, per visibility)
  visibility      "private" (default) or "public"
  date            when the print was done (user-set, optional)
  logged_by_id    FK to the user who created this record
  printer         printer name/model (optional)
  material        filament brand/type description (optional)
  filament_color  color name/hex (optional)
  nozzle_diameter mm (optional)
  layer_height    mm (optional)
  supports        whether supports were used (optional)
  success         True = success, False = failure, None = unrecorded
  rating          1–5 stars (optional)
  --- parsed from gcode on upload ---
  filament_length_mm  filament required, mm (best-effort parse)
  filament_weight_g   filament weight, g (best-effort parse)
  estimated_print_time_s  estimated time, seconds (best-effort parse)
  --- file attachments (relative to item dir) ---
  gcode_file_path path to the .gcode/.gco file in prints/
  print_photo_path path to the photo in prints/

All fields except item_id, visibility, and timestamps are optional.
The gcode parsing is best-effort; absent fields are NULL.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PrintRecord(Base):
    __tablename__ = "print_records"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Item this print belongs to
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Who logged this
    logged_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Note and visibility
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "private" | "public"
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private"
    )

    # When the print happened (user-set)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Structured settings (all optional)
    printer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    material: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filament_color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nozzle_diameter: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    supports: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # True = success, False = failure, None = unrecorded
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # 1–5 rating (user-set)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # gcode-parsed fields (best-effort, nullable)
    filament_length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    filament_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_print_time_s: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # File attachments (relative to item dir, e.g. "prints/job.gcode")
    gcode_file_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    print_photo_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    item: Mapped["Item"] = relationship("Item")  # noqa: F821
    logged_by: Mapped["User | None"] = relationship("User")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<PrintRecord id={self.id} item_id={self.item_id} "
            f"visibility={self.visibility!r}>"
        )
