"""Phase 10a hardening — performance indexes.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-27

Missing indexes identified by the Phase 10a static query audit:

1. item_tags(tag_id) — the PK is (item_id, tag_id); Postgres cannot use that
   index for queries that filter by tag_id alone (e.g., tag-filter browse).
   Without this index every tag-filter query does a full item_tags seq-scan.

2. items(creator_id) — used for creator browse (`WHERE creator_id = X`).
   Already has ix_items_library_id; creator_id was not indexed.

3. items(created_at DESC) — the default catalog sort is `created_at DESC`.
   Without this index every paginated list does a full items seq-scan + sort.

4. items(updated_at DESC) — used by `sort=updated_at_desc`.

5. items(title) — used by `sort=title_asc` and `sort=title_desc`.

6. share_links(created_by_id) — used in list/revoke/audit queries that filter
   by the owner of the link.  Currently only has ix_share_links_token,
   ix_share_links_item_id, and ix_share_links_scope.

7. print_records(item_id, visibility) — compound index for the public-share
   view query (`WHERE item_id = X AND visibility = 'public'`).  The existing
   single-column indexes ix_print_records_item_id and ix_print_records_visibility
   are less efficient for this combined filter.

8. download_bundles(item_id, status, expires_at) — hot path for the "reuse or
   create" logic in the downloads + shares routers.

All indexes are created with IF NOT EXISTS so the migration is safe to re-run.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. item_tags: tag-first lookup (tag browse / tag filter)
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_item_tags_tag_id ON item_tags (tag_id)"
    ))

    # 2. items: creator filter
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_items_creator_id ON items (creator_id)"
    ))

    # 3. items: default sort (created_at DESC)
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_items_created_at ON items (created_at DESC)"
    ))

    # 4. items: updated_at sort
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_items_updated_at ON items (updated_at DESC)"
    ))

    # 5. items: title sort
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_items_title ON items (title)"
    ))

    # 6. share_links: owner filter
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_share_links_created_by_id ON share_links (created_by_id)"
    ))

    # 7. print_records: compound public-share query (item_id + visibility)
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_print_records_item_visibility "
        "ON print_records (item_id, visibility)"
    ))

    # 8. download_bundles: compound reuse / cleanup query
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_download_bundles_item_status_expires "
        "ON download_bundles (item_id, status, expires_at)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_download_bundles_item_status_expires"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_print_records_item_visibility"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_share_links_created_by_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_items_title"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_items_updated_at"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_items_created_at"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_items_creator_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_item_tags_tag_id"))
