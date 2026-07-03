"""Migration 0022 — add 'captured' value to imagesource enum.

Adds the ImageSource.captured variant used for images captured from the
in-browser 3D viewer (canvas screenshot saved as an item image).

GOTCHA: PostgreSQL ALTER TYPE ... ADD VALUE cannot run inside a transaction.
We use autocommit_block() so Alembic commits before executing the DDL.

Downgrade: a no-op — PostgreSQL does not support removing enum values.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE imagesource ADD VALUE IF NOT EXISTS 'captured'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values once added.
    pass
