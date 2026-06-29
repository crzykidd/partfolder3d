"""Phase 13 — ai_usage table.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-28

Records token usage from every real AI call.
Columns: id, created_at (indexed), provider, model, action,
         input_tokens, output_tokens, total_tokens, user_id (nullable FK), success.
The created_at index supports efficient windowed queries (24h / 7d / 30d).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("success", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_created_at", table_name="ai_usage")
    op.drop_table("ai_usage")
