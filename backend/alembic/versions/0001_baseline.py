"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-06-27

Empty baseline migration — no tables yet. Models are added in Phase 1+.
"""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401

from alembic import op  # noqa: F401

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Empty baseline — models created in Phase 1+."""
    pass


def downgrade() -> None:
    pass
