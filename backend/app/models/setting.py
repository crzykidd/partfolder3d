"""Setting model — instance and per-subsystem key/value configuration.

value is stored as a JSON string; callers parse/serialize via json.loads/dumps.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Namespaced key, e.g. "instance.name", "scan.auto_mode", "library.tag_depth".
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # JSON-encoded value (use json.loads/dumps).
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
