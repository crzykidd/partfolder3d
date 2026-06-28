"""Phase 4: Job tracking + scheduled-job state tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-27

Changes:
  jobs              — background job records (type, status, progress, payload, log/error,
                      optional item_id FK, timestamps: created/started/finished)
  scheduled_jobs    — recurring-job state (name PK, description, schedule, last/next run,
                      is_running flag; seeded by worker on_startup)

Implementation notes:
- Uses UUID primary key for jobs (gen_random_uuid()).
- JSONB for jobs.payload (flexible task-specific data).
- scheduled_jobs.name is a VARCHAR PK (stable, human-readable job identifier).
- Both tables use raw SQL (same pattern as 0003/0004) to avoid SA enum issues.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- jobs ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            type        VARCHAR(64)  NOT NULL,
            status      VARCHAR(16)  NOT NULL DEFAULT 'queued',
            progress    INTEGER      NOT NULL DEFAULT 0,
            payload     JSONB        NOT NULL DEFAULT '{}',
            log         TEXT,
            error       TEXT,
            item_id     INTEGER      REFERENCES items(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            started_at  TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_jobs_type   ON jobs (type)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs (status)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_jobs_item_id ON jobs (item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_jobs_created_at ON jobs (created_at DESC)"
    ))

    # ---- scheduled_jobs ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            name             VARCHAR(64)  PRIMARY KEY,
            description      VARCHAR(256) NOT NULL DEFAULT '',
            schedule         VARCHAR(64)  NOT NULL DEFAULT '',
            last_run_at      TIMESTAMPTZ,
            last_run_status  VARCHAR(16),
            last_run_error   TEXT,
            next_run_at      TIMESTAMPTZ,
            is_running       BOOLEAN      NOT NULL DEFAULT FALSE,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS scheduled_jobs"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_jobs_created_at"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_jobs_item_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_jobs_status"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_jobs_type"))
    op.execute(sa.text("DROP TABLE IF EXISTS jobs"))
