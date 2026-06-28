"""ChangeLog model — human-readable record of every automated/approved change (PRD §8.3)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ChangeSource(str, enum.Enum):
    auto = "auto"
    review_approved = "review_approved"
    per_item_rescan = "per_item_rescan"


class ChangeLog(Base):
    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    behavior: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    before_state: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    # "auto" | "review_approved" | "per_item_rescan"
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<ChangeLog id={self.id} behavior={self.behavior!r} type={self.change_type!r}>"
