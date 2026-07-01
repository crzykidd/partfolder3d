"""Argon2id password hashing via passlib.

Params (see docs/decisions.md):
  - time_cost=2   (number of iterations)
  - memory_cost=65536  (64 MiB)
  - parallelism=2
  - hash_len=32
  - salt_len=16

These are moderate defaults suitable for a personal/team app on a single server.
They can be raised without migration: passlib detects "needs rehash" automatically
when the stored hash was generated with weaker params.

All callers should use hash_password() and verify_password() only.
Never touch passlib's CryptContext directly outside this module.
"""

from passlib.context import CryptContext

# Centralised CryptContext — the single source of truth for hashing strategy.
_ctx = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__type="ID",       # argon2id
    argon2__time_cost=2,
    argon2__memory_cost=65536,  # 64 MiB
    argon2__parallelism=2,
    argon2__hash_len=32,
    argon2__salt_len=16,
)


def hash_password(plaintext: str) -> str:
    """Return an argon2id hash string for *plaintext*."""
    return _ctx.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True if *plaintext* matches *hashed*, False otherwise.

    Never raises on bad passwords — always returns a bool.
    """
    return _ctx.verify(plaintext, hashed)


def needs_rehash(hashed: str) -> bool:
    """Return True if *hashed* was produced with weaker params and should be updated."""
    return _ctx.needs_update(hashed)
