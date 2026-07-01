"""Phase 14 — add 'render' value to imagesource enum.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-28

Postgres does not allow ALTER TYPE ... ADD VALUE inside a transaction.
We use an autocommit block so the DDL runs outside any surrounding transaction.

Downgrade note: Postgres does not support removing enum values without
recreating the type.  The downgrade is intentionally a no-op — the extra
value is harmless if the migration is ever rolled back and rows with
source='render' will no longer be created (but existing ones remain).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction on Postgres.
    # Use autocommit_block() so Alembic commits the open transaction before
    # issuing the DDL, then continues in autocommit mode for this block.
    with op.get_context().autocommit_block():
        # Idempotent: only add if the value does not already exist.
        op.execute(
            sa.text(
                "DO $$ BEGIN "
                "IF NOT EXISTS ("
                "  SELECT 1 FROM pg_enum "
                "  JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                "  WHERE pg_type.typname = 'imagesource' "
                "    AND pg_enum.enumlabel = 'render'"
                ") THEN "
                "  ALTER TYPE imagesource ADD VALUE 'render'; "
                "END IF; "
                "END $$;"
            )
        )


def downgrade() -> None:
    # Postgres does not support removing enum values without recreating the type.
    # A no-op downgrade is correct here — the value is harmless when unused.
    # Recorded in docs/decisions.md.
    pass
