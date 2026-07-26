"""Migration 0026 — generated-asset linkage on files.

Adds ``generated_from_file_id`` (self-referential FK, SET NULL on delete) and
``generated_source_sha256`` to ``files``, so a server-compiled derived asset
(v1: the STL OpenSCAD compiles from a ``.scad`` source, issue #46) can be
recorded as clearly linked to — and generated from — its source File, with
the source's sha256 at compile time so a later pass can detect staleness
without re-running the compile. See prompts/done/2026-07-25-server-side-scad-render.md
and docs/decisions.md.

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("generated_from_file_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "files",
        sa.Column("generated_source_sha256", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_files_generated_from_file_id",
        "files",
        ["generated_from_file_id"],
    )
    op.create_foreign_key(
        "fk_files_generated_from_file_id",
        "files",
        "files",
        ["generated_from_file_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_files_generated_from_file_id", "files", type_="foreignkey")
    op.drop_index("ix_files_generated_from_file_id", table_name="files")
    op.drop_column("files", "generated_source_sha256")
    op.drop_column("files", "generated_from_file_id")
