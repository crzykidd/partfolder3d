"""Key generation and shard derivation for item storage.

Key format: 7-character lowercase base32 string derived from 4 random bytes.

Alphabet: standard base32 (a–z, 2–7), unambiguous by construction — no '0',
'1', '8', '9', or letter confusables beyond the 5-bit alphabet.

Length: 7 characters (4 bytes × 8 bits / 5 bits per char = 6.4, padded to 7 +
one '=' which is stripped). Gives 2^35 ≈ 34 billion unique keys — amply large
for a personal/team library and short enough to type.

Shard: first 2 characters of the key (e.g. "ab" → "ab/").
With a 32-char alphabet and 2 shard chars that is 1024 possible shards,
distributing 100k items to ~98 items per shard on average.

Decisions recorded in: docs/decisions.md
"""

import base64
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Re-import lazily to avoid circular imports at module load time.
_ITEM_MODEL = None


def _get_item() -> type:
    global _ITEM_MODEL
    if _ITEM_MODEL is None:
        from ..models.item import Item  # noqa: PLC0415
        _ITEM_MODEL = Item
    return _ITEM_MODEL


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

KEY_LENGTH = 7  # characters in the final key string


def generate_key_raw() -> str:
    """Generate a random 7-character lowercase base32 key.

    Uses 4 random bytes → standard base32 (uppercase A-Z2-7 + one '=') →
    strip padding → lowercase → first 7 characters.

    4 bytes = 32 bits of entropy; base32 encodes 5 bits/char; 32/5 rounds up
    to 7 chars (padded to 8 in standard base32, hence one trailing '=').
    """
    raw = secrets.token_bytes(4)
    encoded = base64.b32encode(raw).decode()  # 8 chars: XXXXXXX=
    return encoded.rstrip("=").lower()         # 7 chars, lowercase


async def generate_unique_key(db: AsyncSession, max_retries: int = 10) -> str:
    """Generate a key that does not already exist in the items table.

    Retries up to `max_retries` times (collision probability ≈ N / 2^35 per
    attempt, effectively zero for any realistic library size).

    Raises:
        RuntimeError: if uniqueness cannot be established after max_retries.
    """
    Item = _get_item()
    for _ in range(max_retries):
        key = generate_key_raw()
        result = await db.execute(select(Item).where(Item.key == key))
        if result.scalar_one_or_none() is None:
            return key
    raise RuntimeError(  # pragma: no cover
        f"Could not generate a unique item key after {max_retries} attempts. "
        "This should never happen at normal library sizes."
    )


# ---------------------------------------------------------------------------
# Shard derivation
# ---------------------------------------------------------------------------

SHARD_LENGTH = 2  # number of key characters used as the shard prefix


def key_shard(key: str) -> str:
    """Return the shard directory name for a key (first 2 characters).

    Example: key "ab3fg72" → shard "ab".
    """
    return key[:SHARD_LENGTH]
