"""Phase 7: Print history + sharing — PrintRecord, ShareLink, ShareAuditEvent;
extend download_bundles with include_print_history + requester_user_id.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-27

Design decisions recorded in docs/decisions.md:
  - PrintRecord: all structured settings fields are nullable; privacy is per-record
    (visibility "private"|"public"), not per-item.  gcode-parsed fields stored
    denormalized on the record for fast stats queries without re-parsing.
  - ShareLink: token is 64-char hex (256-bit entropy, secrets.token_hex(32)).
    Never hashed — the token itself is the credential.  The scope column gates
    what the public endpoint exposes.  expires_at=NULL means never-expires.
  - ShareAuditEvent: BigSerial PK (high-volume on public links).
    Cascade-deletes with the link to avoid orphaned audit rows.
  - download_bundles extended rather than a new table: the include_print_history
    flag changes what the worker zips and needs to travel with the bundle row.
    requester_user_id (plain Integer, no FK) avoids blocking delete-user.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- print_records ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS print_records (
            id                      SERIAL PRIMARY KEY,
            item_id                 INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            logged_by_id            INTEGER REFERENCES users(id) ON DELETE SET NULL,
            note                    TEXT         NULL,
            visibility              VARCHAR(16)  NOT NULL DEFAULT 'private',
            date                    DATE         NULL,
            printer                 VARCHAR(255) NULL,
            material                VARCHAR(255) NULL,
            filament_color          VARCHAR(64)  NULL,
            nozzle_diameter         FLOAT        NULL,
            layer_height            FLOAT        NULL,
            supports                BOOLEAN      NULL,
            success                 BOOLEAN      NULL,
            rating                  INTEGER      NULL,
            filament_length_mm      FLOAT        NULL,
            filament_weight_g       FLOAT        NULL,
            estimated_print_time_s  INTEGER      NULL,
            gcode_file_path         VARCHAR(2048) NULL,
            print_photo_path        VARCHAR(2048) NULL,
            created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_print_records_item_id ON print_records(item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_print_records_logged_by_id"
        " ON print_records(logged_by_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_print_records_visibility"
        " ON print_records(visibility)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_print_records_created_at ON print_records(created_at)"
    ))

    # ---- download_bundles: add Phase 7 columns ----
    op.execute(sa.text(
        "ALTER TABLE download_bundles"
        " ADD COLUMN IF NOT EXISTS include_print_history BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    op.execute(sa.text(
        "ALTER TABLE download_bundles"
        " ADD COLUMN IF NOT EXISTS requester_user_id INTEGER NULL"
    ))

    # ---- share_links ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS share_links (
            id              SERIAL PRIMARY KEY,
            token           VARCHAR(64)  NOT NULL UNIQUE,
            scope           VARCHAR(32)  NOT NULL DEFAULT 'item_design',
            item_id         INTEGER      REFERENCES items(id) ON DELETE CASCADE,
            created_by_id   INTEGER      REFERENCES users(id) ON DELETE SET NULL,
            expires_at      TIMESTAMPTZ  NULL,
            revoked         BOOLEAN      NOT NULL DEFAULT FALSE,
            revoked_at      TIMESTAMPTZ  NULL,
            revoked_by_id   INTEGER      REFERENCES users(id) ON DELETE SET NULL,
            label           VARCHAR(255) NULL,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_share_links_token ON share_links(token)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_share_links_item_id ON share_links(item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_share_links_scope ON share_links(scope)"
    ))

    # ---- share_audit_events ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS share_audit_events (
            id              BIGSERIAL PRIMARY KEY,
            share_link_id   INTEGER      NOT NULL REFERENCES share_links(id) ON DELETE CASCADE,
            event_type      VARCHAR(32)  NOT NULL,
            ip_address      VARCHAR(64)  NULL,
            user_agent      TEXT         NULL,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_share_audit_events_share_link_id"
        " ON share_audit_events(share_link_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_share_audit_events_created_at"
        " ON share_audit_events(created_at)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS share_audit_events CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS share_links CASCADE"))
    op.execute(sa.text(
        "ALTER TABLE download_bundles DROP COLUMN IF EXISTS requester_user_id"
    ))
    op.execute(sa.text(
        "ALTER TABLE download_bundles DROP COLUMN IF EXISTS include_print_history"
    ))
    op.execute(sa.text("DROP TABLE IF EXISTS print_records CASCADE"))
