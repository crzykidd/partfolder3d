"""In-process DB + config backup.

Strategy: in-process dump via SQLAlchemy (no pg_dump, no postgresql-client
needed in the Docker image).  Creates a .tar.gz archive under /data/backups/
containing:
  - metadata.json    : timestamp, version, table names
  - db.json          : all SQL table rows exported as JSON via asyncpg
  - config/secret.key: the instance Fernet key (critical for decrypt)

Trade-off vs pg_dump:
  - PRO: deployment-safe — zero extra apt packages in the image, no PGDG
    repo wrangling, no version-skew risk between postgresql-client and the
    running server.
  - PRO: self-contained — the same Python process that runs the API dumps the
    DB using the same asyncpg driver; no subprocess, no shell injection risk.
  - CON: restore requires running `alembic upgrade head` first, then re-importing
    the JSON data (no binary pg_dump direct restore). For a personal/team asset
    manager this is acceptable; a large-scale SaaS would want pg_dump.

Backup size: the JSON dump is uncompressed table data, then gzip-compressed.
Typical sizes for a personal library (thousands of items): well under 100 MB.

IMPORTANT: Library binary files (STL, OBJ, images, etc.) are intentionally
NOT included.  The user is responsible for backing up /data/library/.
"""

from __future__ import annotations

import gzip
import json
import logging
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

# Tables to export (deterministic order = friendly diffs; FKs resolved by order).
# Omit large blobs that are pointless to back up (none currently, but be explicit).
_EXPORT_TABLES = [
    "users",
    "user_sessions",
    "password_reset_tokens",
    "api_keys",
    "invites",
    "settings",
    "ai_providers",
    "libraries",
    "creators",
    "items",
    "files",
    "images",
    "item_tags",
    "tags",
    "tag_aliases",
    "favorites",
    "download_bundles",
    "jobs",
    "scheduled_jobs",
    "import_sessions",
    "import_session_files",
    "import_session_images",
    "site_capabilities",
    "site_tokens",
    "issues",
    "change_log",
    "review_items",
    "print_records",
    "share_links",
    "share_audit_events",
    "backups",
]

_DEFAULT_RETENTION = 10  # keep last N archives; overridden by setting "backup.retention_count"


def _serialize_value(v: object) -> object:
    """Convert asyncpg / Python types to JSON-serializable form."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "isoformat"):  # date
        return v.isoformat()
    if isinstance(v, bytes):
        return v.hex()
    return v


async def run_db_backup(data_dir: str) -> Path:
    """Export all table rows to a timestamped .tar.gz under {data_dir}/backups/.

    Returns the Path to the created archive.
    Raises on any error (caller records the failure).
    """
    import asyncpg  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.version import __version__  # noqa: PLC0415

    backup_dir = Path(data_dir) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"backup_{ts}.tar.gz"
    archive_path = backup_dir / filename

    # Parse DATABASE_URL: asyncpg uses its own DSN format
    db_url = settings.DATABASE_URL
    # asyncpg DSN: postgresql://user:pass@host:port/db
    # Our URL may be postgresql+asyncpg://...
    asyncpg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn=asyncpg_url)
    try:
        # Export each table
        table_data: dict[str, list[dict]] = {}
        for table in _EXPORT_TABLES:
            try:
                rows = await conn.fetch(f"SELECT * FROM {table}")  # noqa: S608
                table_data[table] = [
                    {k: _serialize_value(v) for k, v in dict(row).items()}
                    for row in rows
                ]
            except Exception as exc:
                log.warning("backup: table %r not found or error: %s", table, exc)
                table_data[table] = []
    finally:
        await conn.close()

    # Build the archive in a temp dir, then move to final path
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # metadata.json
        meta = {
            "created_at": datetime.now(UTC).isoformat(),
            "version": __version__,
            "tables": list(table_data.keys()),
            "note": (
                "Library binary files (STL, OBJ, images, etc.) are NOT included. "
                "Back up /data/library/ separately."
            ),
        }
        (tmp_path / "metadata.json").write_text(
            json.dumps(meta, indent=2, default=str), encoding="utf-8"
        )

        # db.json (gzip-compressed to keep the archive size reasonable)
        db_json = json.dumps(table_data, indent=None, default=str)
        with gzip.open(tmp_path / "db.json.gz", "wt", encoding="utf-8") as gf:
            gf.write(db_json)

        # config/secret.key
        key_path = Path(data_dir) / "config" / "secret.key"
        if key_path.exists():
            config_dir = tmp_path / "config"
            config_dir.mkdir()
            import shutil  # noqa: PLC0415
            shutil.copy2(key_path, config_dir / "secret.key")
        else:
            log.warning("backup: secret.key not found at %s — omitting from archive", key_path)

        # Create the .tar.gz
        with tarfile.open(archive_path, "w:gz") as tf:
            for child in sorted(tmp_path.rglob("*")):
                if child.is_file():
                    arcname = child.relative_to(tmp_path)
                    tf.add(child, arcname=str(arcname))

    log.info("backup: archive created at %s (%d bytes)", archive_path, archive_path.stat().st_size)
    return archive_path


async def prune_old_backups(data_dir: str, keep: int) -> int:
    """Delete old backup archives and DB rows, keeping the `keep` most recent.

    Returns the number of archives deleted.
    """
    import sqlalchemy as sa  # noqa: PLC0415

    from app.db import SessionLocal  # noqa: PLC0415
    from app.models.backup import BackupRecord  # noqa: PLC0415

    async with SessionLocal() as db:
        result = await db.execute(
            sa.select(BackupRecord)
            .where(BackupRecord.status == "ready")
            .order_by(BackupRecord.created_at.desc())
        )
        all_ready = list(result.scalars().all())

    to_prune = all_ready[keep:]
    deleted = 0
    for record in to_prune:
        p = Path(record.path)
        if p.exists():
            try:
                p.unlink()
                deleted += 1
            except OSError as exc:
                log.warning("prune_old_backups: could not delete %s: %s", p, exc)

        async with SessionLocal() as db:
            result2 = await db.execute(
                sa.select(BackupRecord).where(BackupRecord.id == record.id)
            )
            row = result2.scalar_one_or_none()
            if row:
                await db.delete(row)
                await db.commit()

    if deleted:
        log.info("prune_old_backups: deleted %d old archive(s)", deleted)
    return deleted
