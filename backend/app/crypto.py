"""Instance encryption key management and Fernet-based encrypt/decrypt helpers.

The instance key is a Fernet symmetric key stored at DATA_DIR/config/secret.key
(mode 0600). It is generated automatically on first run if absent.

IMPORTANT: Losing the key means all encrypted secrets in the DB (API keys, AI
provider keys, invite/reset tokens, site tokens) must be re-entered. There is no
key escrow. See PRD §18 for the rationale.

Key rotation is a later utility (re-encrypt-all pass); do not build it here.
This module leaves a clear seam: callers use encrypt()/decrypt() and never touch
the key directly — a future rotate() can swap _get_fernet() transparently.
"""

import stat
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------


def _key_path() -> Path:
    """Return the path to the instance secret key file."""
    return Path(settings.DATA_DIR) / "config" / "secret.key"


def ensure_key() -> None:
    """Create the instance key if it does not exist.

    Called once at application startup (lifespan) so the key is always present
    before the first request that needs encryption.

    The key file is created with mode 0600 (owner read/write only).
    """
    path = _key_path()
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    # Write atomically: write to a temp file, chmod, then rename.
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(key)
    tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    tmp.rename(path)


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Load the Fernet instance from the key file (cached after first load).

    Call ensure_key() before the first request so this never runs against a
    missing file at startup. Tests point DATA_DIR at a temp dir via config.
    """
    key_bytes = _key_path().read_bytes()
    return Fernet(key_bytes.strip())


def _reset_fernet_cache() -> None:
    """Clear the cached Fernet instance (used in tests when rotating temp keys)."""
    _get_fernet.cache_clear()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string with the instance Fernet key.

    Returns a URL-safe base64-encoded ciphertext string suitable for DB storage.
    """
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext string returned by encrypt().

    Raises:
        cryptography.fernet.InvalidToken: if the ciphertext is tampered or the
            wrong key is used. Callers should treat this as a fatal config error
            (lost/rotated key) and surface a clear error to the admin.
    """
    return _get_fernet().decrypt(ciphertext.encode()).decode()


__all__ = ["ensure_key", "encrypt", "decrypt", "InvalidToken", "_reset_fernet_cache"]
