"""Migration 0019 — job lifecycle columns.

Adds to `jobs`:
  • arq_job_id  VARCHAR(64)  NULL  (indexed) — arq job id for mid-flight abort.
  • retry_of_job_id  UUID  NULL  FK → jobs.id ON DELETE SET NULL  (indexed) —
    links a retry/restart to the job it replaces.
  • archived_at  TIMESTAMPTZ  NULL  (indexed) — set when a job is cleared/archived.

Downgrade: drops archived_at, retry_of_job_id (+ FK), arq_job_id (+ indexes).

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. arq_job_id — track the arq queue job id for abort support
    op.add_column(
        "jobs",
        sa.Column("arq_job_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_jobs_arq_job_id", "jobs", ["arq_job_id"])

    # 2. retry_of_job_id — self-referential FK linking a retry to its predecessor
    op.add_column(
        "jobs",
        sa.Column(
            "retry_of_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index("ix_jobs_retry_of_job_id", "jobs", ["retry_of_job_id"])
    op.create_foreign_key(
        "fk_jobs_retry_of_job_id",
        "jobs",
        "jobs",
        ["retry_of_job_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. archived_at — cleared/archived timestamp for the archive list
    op.add_column(
        "jobs",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_archived_at", "jobs", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_archived_at", table_name="jobs")
    op.drop_column("jobs", "archived_at")

    op.drop_constraint("fk_jobs_retry_of_job_id", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_retry_of_job_id", table_name="jobs")
    op.drop_column("jobs", "retry_of_job_id")

    op.drop_index("ix_jobs_arq_job_id", table_name="jobs")
    op.drop_column("jobs", "arq_job_id")
