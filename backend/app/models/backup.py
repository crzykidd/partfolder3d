"""BackupRecord model — tracks DB+config backup archives.

Each backup job creates one row here to record the archive path, size,
and outcome.  Retention pruning (keep the N most recent) happens at the
end of each backup run.

The backup itself is a .tar.gz under /data/backups/ containing:
  - db.json          : all SQL table data exported via SQLAlchemy/asyncpg
  - config/secret.key: the instance Fernet encryption key
  - metadata.json    : timestamp, version, table checksums

Library binary files are intentionally NOT included — the user owns
their backup strategy for /data/library/.  This is prominently noted
in the admin UI callout.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BackupRecord(Base):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Filename without directory (e.g. "backup_2026-06-27T04:00:00.tar.gz")
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    # Absolute path to the .tar.gz file on disk.
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Compressed archive size in bytes (None while pending).
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # "pending" → "ready" → "failed"
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<BackupRecord id={self.id} filename={self.filename!r} status={self.status}>"
