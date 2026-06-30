"""Job model — background job tracking (PRD §4, §8.3).

Created by worker tasks to record status and progress.
Visible in the admin job/queue monitor.

Status flow: queued → running → succeeded | failed | cancelled | superseded
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Descriptive type string, e.g. "render", "zip_bundle", "expired_zip_cleanup"
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # queued | running | succeeded | failed | cancelled | superseded
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", index=True
    )
    # 0–100; updated by the worker task as it progresses
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Arbitrary task-specific payload (item_id, file path, etc.)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Accumulated log text (newline-separated)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Error message on failure
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional FK to the item this job operates on (for render / ZIP jobs)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # arq internal job id — used to abort running jobs via arq's abort API
    arq_job_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    # Links a retry/restart to the original job it replaces (for supersede-on-success)
    retry_of_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Set when a job is cleared/archived; excluded from the default list
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} type={self.type!r} status={self.status!r}>"
