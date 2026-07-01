"""Phase 9: Admin — backups table for DB+config backup records.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-27

New table:
  backups — tracks each DB+config backup archive (path, size, status, error).
             Used by the backup scheduled job and the admin backup API.

No schema changes to existing tables are required for Phase 9 — tag admin
(aliases, categories, merge, approve) all operate on the existing tags /
tag_aliases / item_tags tables.  Site capability admin uses the existing
site_capabilities / site_tokens tables.  API key management already exists.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS backups (
            id          SERIAL PRIMARY KEY,
            filename    VARCHAR(512)  NOT NULL,
            path        VARCHAR(2048) NOT NULL,
            size_bytes  BIGINT        NULL,
            status      VARCHAR(32)   NOT NULL DEFAULT 'pending',
            error       TEXT          NULL,
            created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_backups_created_at ON backups(created_at)"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS backups"))
