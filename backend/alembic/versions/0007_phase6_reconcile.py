"""Phase 6: Reconciliation / scan engine — issues, change log, review items.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-27

Changes:
  issues       — detected problems (conflict, dead-link, corruption, orphan, …)
  change_log   — human-readable record of every automated / approved change
  review_items — proposed changes awaiting user approval

Design decisions recorded in docs/decisions.md:
  - Issue/ChangeLog/ReviewItem are separate tables (not a single polymorphic table)
    because their query patterns differ: issues are filtered by status+type,
    change_log is an append-only feed, review_items need a pending-only fast path.
  - All FKs to items.id use ON DELETE SET NULL so losing an item doesn't erase
    the audit trail.
  - proposed_action is JSONB so the worker can deserialize and apply it without
    re-reading the sidecar or re-running the engine.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- issues ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS issues (
            id          SERIAL PRIMARY KEY,
            issue_type  VARCHAR(64)  NOT NULL,
            severity    VARCHAR(16)  NOT NULL DEFAULT 'warning',
            status      VARCHAR(16)  NOT NULL DEFAULT 'open',
            item_id     INTEGER      REFERENCES items(id) ON DELETE SET NULL,
            detail      TEXT         NOT NULL,
            suggested_action TEXT    NULL,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            resolved_at TIMESTAMPTZ  NULL
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_issues_status_type ON issues(status, issue_type)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_issues_item_id ON issues(item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_issues_created_at ON issues(created_at)"
    ))

    # ---- change_log ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS change_log (
            id          SERIAL PRIMARY KEY,
            behavior    VARCHAR(64)  NOT NULL,
            change_type VARCHAR(128) NOT NULL,
            item_id     INTEGER      REFERENCES items(id) ON DELETE SET NULL,
            summary     TEXT         NOT NULL,
            before_state JSONB       NULL,
            after_state  JSONB       NULL,
            source      VARCHAR(32)  NOT NULL DEFAULT 'auto',
            actor       VARCHAR(255) NOT NULL DEFAULT 'system',
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_change_log_behavior_created"
        " ON change_log(behavior, created_at)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_change_log_item_id ON change_log(item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_change_log_created_at ON change_log(created_at)"
    ))

    # ---- review_items ----
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS review_items (
            id               SERIAL PRIMARY KEY,
            behavior         VARCHAR(64)  NOT NULL,
            change_type      VARCHAR(128) NOT NULL,
            item_id          INTEGER      REFERENCES items(id) ON DELETE SET NULL,
            summary          TEXT         NOT NULL,
            proposed_action  JSONB        NOT NULL,
            status           VARCHAR(16)  NOT NULL DEFAULT 'pending',
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            resolved_at      TIMESTAMPTZ  NULL,
            resolved_by_id   INTEGER      REFERENCES users(id) ON DELETE SET NULL
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_review_items_status_behavior"
        " ON review_items(status, behavior)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_review_items_item_id ON review_items(item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_review_items_created_at ON review_items(created_at)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS review_items CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS change_log CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS issues CASCADE"))
