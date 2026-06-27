"""Phase 2: libraries, creators, tags, items, files, images.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-27

Tables added:
  libraries, creators, tags, tag_aliases, items, files, images, item_tags

Enum types added:
  tagstatus  (active, pending)
  filerole   (model, zip, image, render, gcode, photo, other)
  imagesource (scraped, uploaded)

Implementation note: uses raw SQL (sa.text) throughout — same pattern as 0002 —
to avoid SQLAlchemy 2.x + asyncpg auto-CREATE TYPE issues.

The items→images circular FK (items.default_image_id → images.id) is handled by:
  1. Creating items WITHOUT default_image_id.
  2. Creating images (references items.id).
  3. ALTERing items to ADD default_image_id FK.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- enum types ----
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE tagstatus AS ENUM ('active', 'pending'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    ))
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE filerole AS ENUM "
        "('model', 'zip', 'image', 'render', 'gcode', 'photo', 'other'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    ))
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE imagesource AS ENUM ('scraped', 'uploaded'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    ))

    # ---- libraries ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS libraries (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(255)  NOT NULL,
            mount_path  VARCHAR(1024) NOT NULL UNIQUE,
            enabled     BOOLEAN       NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_libraries_mount_path ON libraries (mount_path)"
    ))

    # ---- creators ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS creators (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(512)  NOT NULL,
            profile_url VARCHAR(2048),
            source_site VARCHAR(255),
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_creators_user_id ON creators (user_id)"
    ))

    # ---- tags ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS tags (
            id               SERIAL PRIMARY KEY,
            name             VARCHAR(512) NOT NULL UNIQUE,
            category         VARCHAR(255),
            popularity_count INTEGER      NOT NULL DEFAULT 0,
            status           tagstatus    NOT NULL DEFAULT 'active',
            created_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_tags_name ON tags (name)"
    ))

    # ---- tag_aliases ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS tag_aliases (
            id      SERIAL PRIMARY KEY,
            alias   VARCHAR(512) NOT NULL UNIQUE,
            tag_id  INTEGER      NOT NULL REFERENCES tags(id) ON DELETE CASCADE
        )
    """))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_tag_aliases_alias ON tag_aliases (alias)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_tag_aliases_tag_id ON tag_aliases (tag_id)"
    ))

    # ---- items (WITHOUT default_image_id first — added after images) ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS items (
            id               SERIAL PRIMARY KEY,
            key              VARCHAR(16)   NOT NULL UNIQUE,
            title            VARCHAR(1024) NOT NULL,
            slug             VARCHAR(1024) NOT NULL,
            description      TEXT,
            source_url       VARCHAR(2048),
            source_site      VARCHAR(255),
            license          VARCHAR(255),
            creator_id       INTEGER REFERENCES creators(id) ON DELETE SET NULL,
            library_id       INTEGER       NOT NULL REFERENCES libraries(id) ON DELETE RESTRICT,
            dir_path         VARCHAR(2048) NOT NULL,
            schema_version   INTEGER       NOT NULL DEFAULT 1,
            created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_items_key ON items (key)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_items_library_id ON items (library_id)"))

    # ---- images ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS images (
            id          SERIAL PRIMARY KEY,
            item_id     INTEGER      NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            path        VARCHAR(2048) NOT NULL,
            source      imagesource  NOT NULL,
            is_default  BOOLEAN      NOT NULL DEFAULT FALSE,
            "order"     INTEGER      NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_images_item_id ON images (item_id)"
    ))

    # ---- items.default_image_id — circular FK, added after images table exists ----
    op.execute(sa.text("""
        ALTER TABLE items
            ADD COLUMN IF NOT EXISTS default_image_id INTEGER
                CONSTRAINT fk_items_default_image REFERENCES images(id) ON DELETE SET NULL
    """))

    # ---- files ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS files (
            id              SERIAL PRIMARY KEY,
            item_id         INTEGER       NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            path            VARCHAR(2048) NOT NULL,
            role            filerole      NOT NULL,
            size            BIGINT        NOT NULL,
            sha256          VARCHAR(64),
            mtime           TIMESTAMPTZ   NOT NULL,
            last_seen_size  BIGINT        NOT NULL DEFAULT 0,
            last_seen_mtime TIMESTAMPTZ
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_files_item_id ON files (item_id)"))

    # ---- item_tags ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS item_tags (
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
            CONSTRAINT uq_item_tags PRIMARY KEY (item_id, tag_id)
        )
    """))


def downgrade() -> None:
    # Drop in reverse dependency order
    op.execute(sa.text("DROP TABLE IF EXISTS item_tags"))
    op.execute(sa.text("DROP TABLE IF EXISTS files"))
    op.execute(sa.text("ALTER TABLE items DROP COLUMN IF EXISTS default_image_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS images"))
    op.execute(sa.text("DROP TABLE IF EXISTS items"))
    op.execute(sa.text("DROP TABLE IF EXISTS tag_aliases"))
    op.execute(sa.text("DROP TABLE IF EXISTS tags"))
    op.execute(sa.text("DROP TABLE IF EXISTS creators"))
    op.execute(sa.text("DROP TABLE IF EXISTS libraries"))

    op.execute(sa.text("DROP TYPE IF EXISTS imagesource"))
    op.execute(sa.text("DROP TYPE IF EXISTS filerole"))
    op.execute(sa.text("DROP TYPE IF EXISTS tagstatus"))
