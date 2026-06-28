"""Phase 11 — nav_layout per-user preference.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-28

Adds `nav_layout` column (nullable VARCHAR 16) to `users` table.
Values: 'top' | 'side' | NULL.
NULL is resolved to a role-based default at query time:
  admin  → 'side'
  user   → 'top'
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("nav_layout", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "nav_layout")
