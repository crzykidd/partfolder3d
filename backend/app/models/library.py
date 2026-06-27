"""Library model — a registered filesystem mount for storing 3D assets."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Absolute path to the mount point inside the container (e.g. /library/main).
    mount_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["Item"]] = relationship(  # noqa: F821
        "Item", back_populates="library"
    )

    def __repr__(self) -> str:
        return f"<Library id={self.id} name={self.name!r} path={self.mount_path!r}>"
