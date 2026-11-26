"""Migration 0028 — per-user printer profiles.

Creates ``printer_profiles``: named presets of the six print-record settings
fields, owned by a user. Unique (user_id, name); at most one default per user
via a partial unique index.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "printer_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("printer", sa.String(255), nullable=True),
        sa.Column("material", sa.String(255), nullable=True),
        sa.Column("filament_color", sa.String(64), nullable=True),
        sa.Column("nozzle_diameter", sa.Float(), nullable=True),
        sa.Column("layer_height", sa.Float(), nullable=True),
        sa.Column("supports", sa.Boolean(), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_printer_profiles_user_name"),
    )
    op.create_index("ix_printer_profiles_user_id", "printer_profiles", ["user_id"])
    op.create_index(
        "uq_printer_profiles_one_default_per_user",
        "printer_profiles",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index("uq_printer_profiles_one_default_per_user", table_name="printer_profiles")
    op.drop_index("ix_printer_profiles_user_id", table_name="printer_profiles")
    op.drop_table("printer_profiles")
