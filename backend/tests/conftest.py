"""Test fixtures for Phase 1 identity tests.

Database strategy:
  - Uses the ephemeral Postgres container (or whatever DATABASE_URL points to).
  - Each test gets a fresh connection with NullPool (no connection reuse across
    event loops) and a transaction that is rolled back on completion (fast isolation).
  - The migration must already be applied (upgrade head) before running tests.

Crypto strategy:
  - Tests point DATA_DIR at a temp dir so the key file doesn't pollute /data.
  - The Fernet cache is reset between tests to pick up the temp key.
"""

import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)


# ---------------------------------------------------------------------------
# Per-test temp DATA_DIR with a fresh Fernet key
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Any, monkeypatch: Any) -> None:
    """Point DATA_DIR at a per-test temp dir and reset the crypto cache."""
    monkeypatch.setattr("app.config.settings.DATA_DIR", str(tmp_path))
    import app.crypto as crypto_mod

    monkeypatch.setattr(crypto_mod, "_key_path", lambda: tmp_path / "config" / "secret.key")
    crypto_mod._reset_fernet_cache()


# ---------------------------------------------------------------------------
# Async DB session fixture (per test, NullPool + rolls back)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional AsyncSession that rolls back after each test.

    Uses NullPool so each test gets a fresh connection that is not shared
    between asyncio event loops (pytest-asyncio creates one loop per test).
    """
    # NullPool: no connection pooling → new connection per acquire, safe across loops.
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    async with engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
        await conn.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# ASGI test client pointing at the real app, wired to the test session
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient using the app's ASGI interface.

    The app's get_db dependency is overridden to yield the per-test session
    (which will be rolled back after the test).
    """
    from app.auth.deps import get_db
    from app.crypto import ensure_key
    from app.main import app

    # Ensure key exists in the temp data dir
    ensure_key()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
