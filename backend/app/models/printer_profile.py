"""PrinterProfile — a named, per-user preset of print-record settings.

Used to prefill the Log-print form. Each user may have many profiles and at
most one default (enforced by a partial unique index on ``user_id`` WHERE
``is_default``). Profile names are unique per user.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PrinterProfile(Base):
    __tablename__ = "printer_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_printer_profiles_user_name"),
        Index(
            "uq_printer_profiles_one_default_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Same types as PrintRecord (all optional)
    printer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    material: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filament_color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nozzle_diameter: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    supports: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

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
        return f"<PrinterProfile id={self.id} user_id={self.user_id} name={self.name!r}>"
