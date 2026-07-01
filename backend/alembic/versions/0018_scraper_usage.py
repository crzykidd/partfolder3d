"""Migration 0018 — scraper_usage table + scrape_note on import_sessions.

Adds:
  • scraper_usage table: one row per external scraper API call (AgentQL etc.).
    Used for local budget enforcement (AgentQL exposes no usage endpoint).
    Columns: id, created_at (indexed), provider, source_url, success,
    est_cost_usd.

  • import_sessions.scrape_note (Text, nullable): free-text annotation set by
    the worker when agentql was used ("Fetched via AgentQL") or when the
    static scraper was blocked and agentql unavailable/budget-exhausted.
    Displayed as a subtle note in the import wizard.

Downgrade: drops import_sessions.scrape_note; drops scraper_usage table.

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create scraper_usage table
    op.create_table(
        "scraper_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("est_cost_usd", sa.Float, nullable=False, server_default="0.0"),
    )
    op.create_index(
        "ix_scraper_usage_created_at", "scraper_usage", ["created_at"]
    )

    # 2. Add scrape_note column to import_sessions
    op.add_column(
        "import_sessions",
        sa.Column(
            "scrape_note",
            sa.Text,
            nullable=True,
            comment=(
                "Worker-set note about the scrape: 'Fetched via AgentQL' on success, "
                "or a human-readable blocked/budget message.  Null = standard static scrape."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("import_sessions", "scrape_note")
    op.drop_index("ix_scraper_usage_created_at", table_name="scraper_usage")
    op.drop_table("scraper_usage")
