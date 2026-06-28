"""ScheduledJob — state tracking for recurring background jobs (PRD §8.4).

One row per registered cron job; the worker updates last_run_at, last_run_status,
next_run_at, and is_running around each execution.  Rows are seeded by the worker's
on_startup hook so the table is always consistent with the WorkerSettings cron list.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    # Stable identifier — matches the registry key in worker.py
    # e.g. "expired_zip_cleanup", "placeholder_reindex"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    # Human-readable schedule (e.g. "daily at 00:00 UTC")
    schedule: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # "succeeded" | "failed" | None (never run yet)
    last_run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<ScheduledJob name={self.name!r} status={self.last_run_status!r}>"
