"""Per-user API key generation and verification.

Storage strategy (see docs/decisions.md and models/api_key.py):
  - Generate 256 bits of cryptographically random entropy (URL-safe base64).
  - Store SHA-256 hex digest of the raw key for O(1) lookup.
  - The raw key is returned to the caller *once* at creation; never stored.

Incoming Bearer tokens are hashed and looked up in the DB.
"""

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.api_key import ApiKey

_KEY_BYTES = 32  # 256 bits


def generate_raw_key() -> str:
    """Generate a new raw API key (256-bit, URL-safe base64)."""
    return secrets.token_urlsafe(_KEY_BYTES)


def hash_key(raw: str) -> str:
    """Return the SHA-256 hex digest of *raw* (used for DB storage and lookup)."""
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_api_key_record(db: AsyncSession, raw: str) -> ApiKey | None:
    """Look up an active ApiKey row by its raw token.

    Returns None if the key does not exist or is inactive.
    """
    key_hash = hash_key(raw)
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()
