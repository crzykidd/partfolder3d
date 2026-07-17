"""Migration 0024 — import_session_files.selected.

Adds a ``selected`` boolean to ``import_session_files`` (Manyfold connector
Part 2 of 3 — see prompts/2026-07-17-manyfold-2-connector.md). Manyfold model
imports can stage several 3D files at once (e.g. multiple print-ready variants
of the same design); the wizard needs a per-file toggle so the user can
deselect files they don't want before commit without deleting the staged
bytes. Defaults to True so every existing/staged file behaves exactly as
before (all staged files are moved into the item on commit) until a user
explicitly deselects one.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_session_files",
        sa.Column(
            "selected", sa.Boolean, nullable=False, server_default="true"
        ),
    )


def downgrade() -> None:
    op.drop_column("import_session_files", "selected")
