"""Issue model — a detected problem surfaced by the reconcile engine (PRD §8.3)."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IssueType(str, enum.Enum):
    conflict = "conflict"            # sidecar ⇄ DB both changed
    dead_link = "dead_link"          # source URL unreachable
    corruption = "corruption"        # file hash mismatch
    orphan = "orphan"                # dir with no DB row or DB row with no dir
    missing_file = "missing_file"    # file in DB but not on disk
    extra_file = "extra_file"        # file on disk not in DB (review mode)
    sidecar_error = "sidecar_error"  # sidecar parse / sync failure
    other = "other"


class IssueSeverity(str, enum.Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class IssueStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"
    ignored = "ignored"


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Issue id={self.id} type={self.issue_type!r} status={self.status!r}>"
