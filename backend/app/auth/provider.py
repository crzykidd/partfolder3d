"""Auth provider interface — thin seam for future SSO (OIDC/SAML).

Phase 1 implements PasswordAuthProvider only.  Future phases can add
OIDCAuthProvider or SAMLAuthProvider without touching call sites, as long
as they implement the same abstract interface.

The interface is kept deliberately minimal: only what Phase 1 needs.
"""

from abc import ABC, abstractmethod

from .password import hash_password, verify_password

# Precomputed argon2id hash of a throwaway password. When authentication fails
# because the email is unknown, we still run one verify against this hash so the
# unknown-email path costs the same as the wrong-password path — closing the
# timing side channel that would otherwise let an attacker enumerate accounts.
_DUMMY_PASSWORD_HASH = hash_password("pf3d-timing-equalizer")


class AuthProvider(ABC):
    """Abstract interface for an authentication backend."""

    @abstractmethod
    async def authenticate(self, email: str, password: str) -> int | None:
        """Return the user ID if credentials are valid, else None."""
        ...


class PasswordAuthProvider(AuthProvider):
    """Concrete provider: email + argon2id password."""

    def __init__(self, db) -> None:  # type: ignore[type-arg]
        self._db = db

    async def authenticate(self, email: str, password: str) -> int | None:
        """Look up the user by email and verify the password hash.

        Returns the user_id on success, None on failure.
        Import here to avoid circular deps at module load time.
        """
        from sqlalchemy import select

        from ..models.user import User

        result = await self._db.execute(
            select(User).where(User.email == email, User.is_active.is_(True))
        )
        user = result.scalar_one_or_none()
        if user is None:
            # Run a dummy verify so a missing email takes the same time as a
            # wrong password (no early-return timing oracle for enumeration).
            verify_password(password, _DUMMY_PASSWORD_HASH)
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user.id
