"""Migration 0025 — add 'source' value to filerole enum.

Adds the FileRole.source variant used for design-source files (v1: OpenSCAD
`.scad`). See prompts/done/2026-07-25-scad-source-view.md. Named generically
so more source formats can be added later without another enum migration.

GOTCHA: PostgreSQL ALTER TYPE ... ADD VALUE cannot run inside a transaction.
We use autocommit_block() so Alembic commits before executing the DDL.

Downgrade: a no-op — PostgreSQL does not support removing enum values.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE filerole ADD VALUE IF NOT EXISTS 'source'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values once added.
    pass
