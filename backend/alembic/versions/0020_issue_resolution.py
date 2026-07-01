"""Migration 0020 — issue resolution framework: target_path + dedup index.

Adds to `issues`:
  • target_path  VARCHAR(4096)  NULL  — the logical target the issue concerns
    (orphan-dir: the directory path; missing_file/corruption: the file path;
     dead_link: the URL; etc.).  Used for dedup so the reconcile scanner never
     creates duplicate open/ignored issues for the same (type, target_path).

Indexes:
  • ix_issues_target_path  — simple index for lookups by target_path alone.
  • ix_issues_type_target_status  — composite covering index for the dedup
    query: WHERE issue_type = ? AND target_path = ? AND status IN (…).

Downgrade: drops the composite index, simple index, and target_path column.

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add target_path column
    op.add_column(
        "issues",
        sa.Column("target_path", sa.String(4096), nullable=True),
    )

    # 2. Simple index for target_path lookups
    op.create_index("ix_issues_target_path", "issues", ["target_path"])

    # 3. Composite covering index for the dedup query
    op.create_index(
        "ix_issues_type_target_status",
        "issues",
        ["issue_type", "target_path", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_issues_type_target_status", table_name="issues")
    op.drop_index("ix_issues_target_path", table_name="issues")
    op.drop_column("issues", "target_path")
