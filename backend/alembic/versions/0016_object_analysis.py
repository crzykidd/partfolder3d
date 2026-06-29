"""Phase 16 — per-file object analysis (JSONB) + filament estimate settings.

Adds ``object_analysis`` (JSONB, nullable) to the ``files`` table.  This stores
the static per-object breakdown produced by the ``analyze_item`` arq task:
color count, estimated filament grams, volume, and per-object dimensions.

The column is keyed to the file's sha256 — analysis is re-run only when the
file content changes (same sha-cache pattern as renders).

Two instance-level settings are seeded with defaults:
  - ``estimate.filament_density_g_cm3``  (default 1.24, PLA)
  - ``estimate.infill_pct``               (default 15)

These are stored in the ``settings`` table and are admin-editable via
PUT /api/settings/<key>.  The migration seeds them only if they don't exist
so re-running is idempotent.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-29

Downgrade note: drops ``object_analysis`` from ``files``.  The two settings
rows are NOT deleted on downgrade (harmless orphan rows).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_SETTINGS = [
    ("estimate.filament_density_g_cm3", "1.24"),
    ("estimate.infill_pct", "15"),
]


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column(
            "object_analysis",
            JSONB,
            nullable=True,
            comment=(
                "Per-object mesh analysis keyed to the file sha256. "
                "Schema: { analyzed_at, source_hash, objects: [ObjectAnalysis], "
                "total_objects, total_colors, total_est_grams }. "
                "Null until the analyze_item worker task has run."
            ),
        ),
    )

    # Seed default settings (idempotent)
    settings_table = sa.table(
        "settings",
        sa.column("key", sa.String),
        sa.column("value", sa.Text),
    )
    conn = op.get_bind()
    for key, value in _DEFAULT_SETTINGS:
        exists = conn.execute(
            sa.select(sa.literal(1)).where(
                sa.text("key = :k").bindparams(k=key)
            ).select_from(sa.table("settings", sa.column("key")))
        ).scalar_one_or_none()
        if exists is None:
            conn.execute(
                settings_table.insert().values(key=key, value=value)
            )


def downgrade() -> None:
    op.drop_column("files", "object_analysis")
    # Settings rows intentionally left in place.
