"""Phase 1: identity, sessions, API keys, invites, password reset, settings, AI providers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-27

Tables added:
  users, user_sessions, api_keys, invites, password_reset_tokens, settings, ai_providers

Enum types added:
  userrole (admin, user)
  invitestatus (pending, accepted, expired, revoked)
  aiprovidertype (claude, openai, ollama)

Implementation note: uses raw SQL (sa.text) throughout to prevent SQLAlchemy from
auto-issuing CREATE TYPE statements via the named_types machinery, which does not
reliably respect create_type=False in SQLAlchemy 2.x + asyncpg.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- enum types ----
    # DO blocks are idempotent: safe to re-run if a prior migration run failed partway.
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE userrole AS ENUM ('admin', 'user'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    ))
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE invitestatus AS ENUM ('pending', 'accepted', 'expired', 'revoked'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    ))
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE aiprovidertype AS ENUM ('claude', 'openai', 'ollama'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    ))

    # ---- users ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL PRIMARY KEY,
            email       VARCHAR(255) NOT NULL UNIQUE,
            name        VARCHAR(255) NOT NULL,
            role        userrole    NOT NULL DEFAULT 'user',
            password_hash VARCHAR(1024) NOT NULL,
            theme_pref  VARCHAR(16)  NOT NULL DEFAULT 'system',
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)"))

    # ---- user_sessions ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token       VARCHAR(64)  NOT NULL UNIQUE,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            expires_at  TIMESTAMPTZ  NOT NULL,
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            csrf_token  VARCHAR(64)  NOT NULL
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions (user_id)"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_sessions_token ON user_sessions (token)"
    ))

    # ---- api_keys ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            label        VARCHAR(255) NOT NULL,
            key_hash     VARCHAR(64)  NOT NULL UNIQUE,
            scopes       VARCHAR(1024),
            last_used_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            is_active    BOOLEAN      NOT NULL DEFAULT TRUE
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_api_keys_user_id ON api_keys (user_id)"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash)"
    ))

    # ---- invites ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS invites (
            id              SERIAL PRIMARY KEY,
            token_hash      VARCHAR(64)   NOT NULL UNIQUE,
            email           VARCHAR(255)  NOT NULL,
            created_by_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at      TIMESTAMPTZ   NOT NULL,
            status          invitestatus  NOT NULL DEFAULT 'pending',
            accepted_at     TIMESTAMPTZ,
            created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_invites_token_hash ON invites (token_hash)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_invites_email ON invites (email)"
    ))

    # ---- password_reset_tokens ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  VARCHAR(64) NOT NULL UNIQUE,
            expires_at  TIMESTAMPTZ NOT NULL,
            used        BOOLEAN     NOT NULL DEFAULT FALSE,
            revoked     BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id"
        " ON password_reset_tokens (user_id)"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_password_reset_tokens_token_hash"
        " ON password_reset_tokens (token_hash)"
    ))

    # ---- settings ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS settings (
            id          SERIAL PRIMARY KEY,
            key         VARCHAR(255) NOT NULL UNIQUE,
            value       TEXT         NOT NULL,
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_settings_key ON settings (key)"
    ))

    # ---- ai_providers ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS ai_providers (
            id                  SERIAL PRIMARY KEY,
            provider            aiprovidertype NOT NULL,
            endpoint            VARCHAR(512),
            model               VARCHAR(255),
            api_key_encrypted   TEXT,
            enabled             BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS ai_providers"))
    op.execute(sa.text("DROP TABLE IF EXISTS settings"))
    op.execute(sa.text("DROP TABLE IF EXISTS password_reset_tokens"))
    op.execute(sa.text("DROP TABLE IF EXISTS invites"))
    op.execute(sa.text("DROP TABLE IF EXISTS api_keys"))
    op.execute(sa.text("DROP TABLE IF EXISTS user_sessions"))
    op.execute(sa.text("DROP TABLE IF EXISTS users"))

    # Drop enum types after all tables that reference them are gone
    op.execute(sa.text("DROP TYPE IF EXISTS aiprovidertype"))
    op.execute(sa.text("DROP TYPE IF EXISTS invitestatus"))
    op.execute(sa.text("DROP TYPE IF EXISTS userrole"))
