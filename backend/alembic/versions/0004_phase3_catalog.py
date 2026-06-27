"""Phase 3: favorites, download bundles, full-text search vector, path prefix.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-27

Changes:
  users.path_prefix          VARCHAR(1024) NULL — per-user path display rewrite prefix
  items.search_vector        TSVECTOR NULL + GIN index — full-text search (title/desc/tags)
  favorites                  table: user ↔ item stars (per-user, unique)
  download_bundles           table: lightweight ZIP bundle tracking (Phase 3 downloads)

Implementation notes:
- search_vector is NULL on existing rows; populated on the next write to each item.
- Uses raw SQL (same pattern as 0002/0003) to avoid SA enum auto-CREATE issues.
- UUID primary key for download_bundles uses gen_random_uuid() (Postgres 13+).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- users: per-user path prefix ----
    op.execute(sa.text("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS path_prefix VARCHAR(1024)
    """))

    # ---- items: full-text search vector ----
    op.execute(sa.text("""
        ALTER TABLE items
            ADD COLUMN IF NOT EXISTS search_vector TSVECTOR
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_items_search_vector ON items USING GIN (search_vector)"
    ))

    # ---- favorites ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS favorites (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_favorites UNIQUE (user_id, item_id)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_favorites_user_id ON favorites (user_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_favorites_item_id ON favorites (item_id)"
    ))

    # ---- download_bundles ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS download_bundles (
            id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            item_id        INTEGER      NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            status         VARCHAR(16)  NOT NULL DEFAULT 'pending',
            bundle_path    VARCHAR(2048),
            inventory_hash VARCHAR(64),
            error_message  TEXT,
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            expires_at     TIMESTAMPTZ  NOT NULL
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_download_bundles_item_id ON download_bundles (item_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS download_bundles"))
    op.execute(sa.text("DROP TABLE IF EXISTS favorites"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_items_search_vector"))
    op.execute(sa.text("ALTER TABLE items DROP COLUMN IF EXISTS search_vector"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS path_prefix"))
