"""Migration 0021 — add 'embedded' value to imagesource enum.

Adds the ImageSource.embedded variant used for 3MF embedded thumbnails
(extracted from the file's ZIP, not rendered server-side).

GOTCHA: PostgreSQL ALTER TYPE ... ADD VALUE cannot run inside a transaction.
We use autocommit_block() so Alembic commits before executing the DDL.

Downgrade: a no-op — PostgreSQL does not support removing enum values.
Documented here so the reviewer understands the asymmetry intentionally.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE must run outside any transaction block.
    # autocommit_block() commits any open transaction, executes the DDL in
    # autocommit mode, then Alembic resumes its normal transaction for the
    # rest of the migration (nothing else here).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE imagesource ADD VALUE IF NOT EXISTS 'embedded'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values once added.
    # Downgrade is intentionally a no-op.
    # To fully roll back, drop and recreate the type (which requires
    # migrating all dependent columns) — out of scope for this migration.
    pass
