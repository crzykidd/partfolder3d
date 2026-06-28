"""Phase 5: Import wizard — staging tables + site-capability tracking.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-27

Changes:
  import_sessions      — in-progress import state (staging entity; one row per wizard run)
  import_session_files — staged files linked to an import session
  import_session_images — candidate images (URL or staged path) for a session
  site_capabilities    — per-domain metadata/image scrape capability record
  site_tokens          — encrypted auth tokens per domain (Fernet, instance key)

Design decisions recorded in docs/decisions.md:
  - ImportSession is a staging entity (not a job-payload JSON blob) so it can be
    efficiently queried, patched, and listed without loading a full job record.
  - A linked Job row (jobs.id FK) tracks the async processing step.
  - Items are NOT created until the user commits; the item directory is assigned
    from the confirmed title at commit time (no half-named dirs).
  - SiteToken.encrypted_token: Fernet-encrypted; never plaintext in DB.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- import_sessions ----
    # Postgres has no CREATE TYPE IF NOT EXISTS; guard with a DO block so the
    # migration is re-runnable (matches the DROP TYPE IF EXISTS in downgrade()).
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE importsessionstatus AS ENUM
                ('draft', 'processing', 'pending_wizard', 'committed', 'failed', 'cancelled');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """))
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE importsourcetype AS ENUM
                ('upload', 'inbox', 'url');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """))
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS import_sessions (
            id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            status              importsessionstatus NOT NULL DEFAULT 'draft',
            source_type         importsourcetype    NOT NULL,
            source_url          VARCHAR(2048),
            inbox_folder        VARCHAR(4096),
            staging_dir         VARCHAR(4096),
            suggested_title     VARCHAR(512),
            confirmed_title     VARCHAR(512),
            description         TEXT,
            license             VARCHAR(255),
            source_site         VARCHAR(255),
            creator_name        VARCHAR(512),
            creator_profile_url VARCHAR(2048),
            creator_source_site VARCHAR(255),
            creator_is_own_design BOOLEAN NOT NULL DEFAULT FALSE,
            creator_id          INTEGER REFERENCES creators(id) ON DELETE SET NULL,
            tag_state           JSONB,
            default_image_path  VARCHAR(4096),
            library_id          INTEGER REFERENCES libraries(id) ON DELETE SET NULL,
            job_id              UUID    REFERENCES jobs(id)    ON DELETE SET NULL,
            item_id             INTEGER REFERENCES items(id)   ON DELETE SET NULL,
            created_by_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            error               TEXT
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_import_sessions_status"
        " ON import_sessions (status)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_import_sessions_created_by_id"
        " ON import_sessions (created_by_id)"
    ))

    # ---- import_session_files ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS import_session_files (
            id           SERIAL          PRIMARY KEY,
            session_id   UUID            NOT NULL REFERENCES import_sessions(id) ON DELETE CASCADE,
            staged_path  VARCHAR(4096)   NOT NULL,
            original_name VARCHAR(512)   NOT NULL,
            role         VARCHAR(32)     NOT NULL DEFAULT 'model',
            size         INTEGER         NOT NULL DEFAULT 0
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_isf_session_id"
        " ON import_session_files (session_id)"
    ))

    # ---- import_session_images ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS import_session_images (
            id          SERIAL          PRIMARY KEY,
            session_id  UUID            NOT NULL REFERENCES import_sessions(id) ON DELETE CASCADE,
            path        VARCHAR(4096)   NOT NULL,
            is_url      BOOLEAN         NOT NULL DEFAULT FALSE,
            source      VARCHAR(32)     NOT NULL DEFAULT 'upload',
            "order"     INTEGER         NOT NULL DEFAULT 0,
            is_default  BOOLEAN         NOT NULL DEFAULT FALSE,
            CONSTRAINT uq_isi_order UNIQUE (session_id, "order")
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_isi_session_id"
        " ON import_session_images (session_id)"
    ))

    # ---- site_capabilities ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS site_capabilities (
            domain               VARCHAR(255) PRIMARY KEY,
            can_scrape_metadata  BOOLEAN      NOT NULL DEFAULT TRUE,
            can_scrape_images    BOOLEAN      NOT NULL DEFAULT TRUE,
            requires_token       BOOLEAN      NOT NULL DEFAULT FALSE,
            is_manual_only       BOOLEAN      NOT NULL DEFAULT FALSE,
            last_probed_at       TIMESTAMPTZ,
            notes                TEXT,
            created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))

    # ---- site_tokens ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS site_tokens (
            id               SERIAL       PRIMARY KEY,
            domain           VARCHAR(255) NOT NULL UNIQUE,
            encrypted_token  VARCHAR(4096) NOT NULL,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_site_tokens_domain ON site_tokens (domain)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS site_tokens"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_site_tokens_domain"))
    op.execute(sa.text("DROP TABLE IF EXISTS site_capabilities"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_isi_session_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS import_session_images"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_isf_session_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS import_session_files"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_import_sessions_created_by_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_import_sessions_status"))
    op.execute(sa.text("DROP TABLE IF EXISTS import_sessions"))
    op.execute(sa.text("DROP TYPE IF EXISTS importsourcetype"))
    op.execute(sa.text("DROP TYPE IF EXISTS importsessionstatus"))
