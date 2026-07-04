"""Shared instance-setting read helpers.

Instance settings live as JSON-encoded key/value rows in the ``settings`` table
(see :mod:`app.models.setting`).  Most call sites read a single key directly, but
boolean settings share the same parse/default handling, so it lives here for reuse.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.setting import Setting

# Key for the "auto-approve new tags" instance setting (#31).  When true, tags
# minted during an import commit land ``active`` instead of ``pending`` — skipping
# the admin approval queue.  Stored as a JSON boolean; default (absent) is false.
TAGS_AUTO_APPROVE_KEY = "tags.auto_approve"


async def get_bool_setting(
    db: AsyncSession, key: str, default: bool = False
) -> bool:
    """Read a boolean instance setting, returning *default* when unset/malformed.

    The value is stored JSON-encoded; only a real JSON boolean counts — any other
    stored type (or a missing row / malformed JSON) yields *default*.
    """
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        return default
    try:
        value = json.loads(row.value)
    except (ValueError, TypeError):
        return default
    return value if isinstance(value, bool) else default


async def get_tags_auto_approve(db: AsyncSession, default: bool = False) -> bool:
    """Return whether new import-minted tags should be auto-approved (#31)."""
    return await get_bool_setting(db, TAGS_AUTO_APPROVE_KEY, default)
