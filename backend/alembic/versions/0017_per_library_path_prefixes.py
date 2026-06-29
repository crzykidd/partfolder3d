"""Migration 0017 — per-library × per-OS path prefixes.

Add ``users.path_prefixes`` (JSONB, nullable) holding the per-user map:
  { "<library_id>": { "windows": "<path>" | null, "posix": "<path>" | null } }

Migrates any existing ``users.path_prefix`` value into the new column, applying
it to *all* current libraries under the OS inferred from the string
(contains backslash → windows; else posix).

``users.path_prefix`` is kept (now deprecated / unused) so a downgrade is
trivially safe and no existing data is lost.

Downgrade: drop ``users.path_prefixes`` only.

The migration helper logic lives in ``app.path_prefix_utils.infer_prefix_map``
so it can be unit-tested independently.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-29
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# Ensure the backend package is on sys.path so we can import app.*
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.path_prefix_utils import infer_prefix_map  # noqa: E402

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add new column.
    op.add_column(
        "users",
        sa.Column(
            "path_prefixes",
            JSONB,
            nullable=True,
            comment=(
                "Per-library × per-OS local path prefix map.  "
                "Schema: { \"<library_id>\": { \"windows\": str|null, \"posix\": str|null } }.  "
                "Null = no prefixes configured."
            ),
        ),
    )

    # 2. Migrate existing path_prefix values (best-effort, data migration).
    conn = op.get_bind()

    # Collect users with a legacy prefix.
    users_with_prefix = conn.execute(
        sa.text(
            "SELECT id, path_prefix FROM users"
            " WHERE path_prefix IS NOT NULL AND path_prefix != ''"
        )
    ).fetchall()

    if users_with_prefix:
        # Collect all library IDs (enabled or not — we migrate for all).
        library_rows = conn.execute(sa.text("SELECT id FROM libraries")).fetchall()
        library_ids = [row[0] for row in library_rows]

        if library_ids:
            for user_id, path_prefix in users_with_prefix:
                prefix_map = infer_prefix_map(path_prefix, library_ids)
                conn.execute(
                    sa.text(
                        "UPDATE users SET path_prefixes = :pmap::jsonb WHERE id = :uid"
                    ),
                    {"pmap": json.dumps(prefix_map), "uid": user_id},
                )


def downgrade() -> None:
    op.drop_column("users", "path_prefixes")
    # users.path_prefix is intentionally left in place on downgrade.
