"""Migration 0027 — supersede orphaned queued extract_archives Job rows.

``extract_archives`` used ``create_job`` instead of ``claim_or_create_job``, so
the ``queued`` row written at enqueue time was never claimed and stayed
``queued`` forever (the worker's own row ran separately). A ``queued``
extract_archives row with a LATER extract_archives row for the same item is
provably orphaned; mark those ``superseded``. Lone queued rows (possibly
genuinely pending) are left alone. Data-only; idempotent; downgrade is a no-op.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPERSEDE_ORPHANED_SQL = """
UPDATE jobs AS q
SET status = 'superseded',
    finished_at = now(),
    error = 'orphaned queued row (extract_archives claim bug) - superseded by migration 0027'
WHERE q.type = 'extract_archives'
  AND q.status = 'queued'
  AND EXISTS (
      SELECT 1 FROM jobs AS later
      WHERE later.type = 'extract_archives'
        AND later.item_id = q.item_id
        AND later.created_at > q.created_at
        AND later.id <> q.id
  )
"""


def upgrade() -> None:
    op.execute(sa.text(SUPERSEDE_ORPHANED_SQL))


def downgrade() -> None:
    # Data-only migration: superseded rows are not restored.
    pass
