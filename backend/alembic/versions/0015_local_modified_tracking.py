"""Phase 15 — add local-modification tracking columns to items.

Adds source_baseline (JSONB), source_version (text), locally_modified (bool),
locally_modified_at (timestamptz), and modified_override (text) to the items table.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-29

Downgrade note: drops all five columns.  Any baseline hashes and modification
state are lost on downgrade; no data migration is needed because these columns
are ephemeral tracking data that will be regenerated on the next import/scan.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column(
            "source_baseline",
            JSONB,
            nullable=True,
            comment=(
                "Snapshot of model-file path→sha256 at import commit. "
                "Null for items without a source_url or created before this feature."
            ),
        ),
    )
    op.add_column(
        "items",
        sa.Column(
            "source_version",
            sa.String(1024),
            nullable=True,
            comment=(
                "Best-effort version/updated marker from the scraper at import time. "
                "Reserved for the future upstream-update check (type 2). May be null."
            ),
        ),
    )
    op.add_column(
        "items",
        sa.Column(
            "locally_modified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=(
                "Set by the scan engine when current model files diverge from source_baseline."
            ),
        ),
    )
    op.add_column(
        "items",
        sa.Column(
            "locally_modified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when divergence was last detected (or cleared).",
        ),
    )
    op.add_column(
        "items",
        sa.Column(
            "modified_override",
            sa.String(16),
            nullable=True,
            comment=(
                "Manual override: 'modified' | 'original' | null. "
                "Effective state = override if set, else locally_modified."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("items", "modified_override")
    op.drop_column("items", "locally_modified_at")
    op.drop_column("items", "locally_modified")
    op.drop_column("items", "source_version")
    op.drop_column("items", "source_baseline")
