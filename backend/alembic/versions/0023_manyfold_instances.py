"""Migration 0023 — manyfold_instances table.

Adds the manyfold_instances table backing the Manyfold connector config (Part 1
of 3 — see prompts/2026-07-17-manyfold-1-config.md). Stores per-instance OAuth
client_credentials (client_id plaintext, client_secret Fernet-encrypted) so
Part 2 can fetch a bearer token and download files from a registered Manyfold
instance.

Columns: id, base_url, domain (unique index — matched against an import URL's
domain in Part 2), display_name, client_id, client_secret_enc, scopes,
enabled, last_connected_at, notes, created_at, updated_at.

Downgrade: drops the table (and its unique index).

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "manyfold_instances",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("client_secret_enc", sa.Text, nullable=True),
        sa.Column(
            "scopes", sa.String(255), nullable=False, server_default="public read"
        ),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
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
    )
    op.create_index(
        "ix_manyfold_instances_domain",
        "manyfold_instances",
        ["domain"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_manyfold_instances_domain", table_name="manyfold_instances")
    op.drop_table("manyfold_instances")
