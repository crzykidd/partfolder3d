"""Test fixtures for PartFolder 3D backend tests.

Database strategy:
  - Uses the ephemeral Postgres container (or whatever DATABASE_URL points to).
  - Each test gets a fresh connection with NullPool (no connection reuse across
    event loops) and a transaction that is rolled back on completion (fast isolation).
  - The migration must already be applied (upgrade head) before running tests.
  - Under pytest-xdist (PYTEST_XDIST_WORKER set), each worker gets its own
    per-worker database (e.g. partfolder3d_gw0) that is created and migrated at
    worker-session start.  DATABASE_URL is rewritten at the top of this file —
    before any app module is imported — so both the fixture engine and the app's
    own SessionLocal (app.db) resolve to the same per-worker database.

Crypto strategy:
  - Tests point DATA_DIR at a temp dir so the key file doesn't pollute /data.
  - The Fernet cache is reset between tests to pick up the temp key.
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Per-worker DATABASE_URL override — MUST run before any app.* import.
#
# When PYTEST_XDIST_WORKER is set (e.g. "gw0", "gw1"), rewrite DATABASE_URL
# to point at a per-worker database so workers never share a single DB and
# never contend on each other's transactions.
#
# When the env var is absent (serial run / -n 0), leave DATABASE_URL untouched
# so the existing behaviour (single DB, rollback isolation) is preserved exactly.
# ---------------------------------------------------------------------------
_XDIST_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "")
if _XDIST_WORKER:
    _base_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
    )
    _base_db_name = _base_url.rsplit("/", 1)[-1]
    _worker_db_name = f"{_base_db_name}_{_XDIST_WORKER}"
    _worker_db_url = _base_url.rsplit("/", 1)[0] + "/" + _worker_db_name
    os.environ["DATABASE_URL"] = _worker_db_url

# Now it is safe to capture TEST_DB_URL — it resolves to the per-worker URL
# when running under xdist, or the base URL when running serially.
TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d",
)


# ---------------------------------------------------------------------------
# Per-worker DB setup (session-scoped, xdist only)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _worker_db_setup() -> None:
    """Create and migrate the per-worker Postgres DB when running under xdist.

    No-op in serial runs (PYTEST_XDIST_WORKER is unset).  Each xdist worker
    calls this once at session start: it drops any stale DB from a previous run,
    creates a fresh one, then runs `alembic upgrade head` against it.

    Uses asyncio.run() (safe here because no event loop is running at session
    fixture setup time — per-test loops are created later by pytest-asyncio).
    """
    if not _XDIST_WORKER:
        return  # serial run: assume DB already has migrations applied

    import shutil
    import subprocess
    import sys

    from sqlalchemy import text

    worker_db_url: str = os.environ["DATABASE_URL"]
    worker_db_name = worker_db_url.rsplit("/", 1)[-1]
    # Maintenance URL: connect to the "postgres" system DB (always exists)
    maint_url = worker_db_url.rsplit("/", 1)[0] + "/postgres"

    async def _create_db() -> None:
        engine = create_async_engine(
            maint_url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
        )
        async with engine.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{worker_db_name}"'))
            await conn.execute(text(f'CREATE DATABASE "{worker_db_name}"'))
        await engine.dispose()

    asyncio.run(_create_db())

    # Run alembic migrations via the CLI binary (not the programmatic API): the
    # backend/alembic/ dir has __init__.py and shadows the installed alembic package
    # when imported with cwd=backend_dir on sys.path.  Resolve the binary next to the
    # interpreter RUNNING the tests so it works both for a local .venv AND on CI
    # (system / hostedtool Python, where no backend/.venv exists); fall back to PATH.
    backend_dir = str(Path(__file__).parent.parent)
    _alembic_candidate = Path(sys.executable).with_name("alembic")
    alembic_bin = (
        str(_alembic_candidate)
        if _alembic_candidate.exists()
        else (shutil.which("alembic") or "alembic")
    )
    result = subprocess.run(
        [alembic_bin, "upgrade", "head"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed for worker {_XDIST_WORKER}:\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Per-test temp DATA_DIR with a fresh Fernet key
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Any, monkeypatch: Any) -> None:
    """Point DATA_DIR at a per-test temp dir and reset the crypto cache.

    Also sets COOKIE_SECURE=False so httpx (which uses http://test as the base
    URL) actually sends session and CSRF cookies.  In production COOKIE_SECURE
    must be True (HTTPS only); in tests we never use a real TLS connection.
    """
    monkeypatch.setattr("app.config.settings.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.config.settings.COOKIE_SECURE", False)
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
# Shared arq pool stand-in
# ---------------------------------------------------------------------------
@pytest.fixture
def arq_pool() -> Any:
    """Stand-in for the process-wide arq pool (``app.state.arq_pool``).

    The real pool is created at app lifespan against Redis; the ASGI test
    transport never runs lifespan and there is no Redis in tests, so every
    enqueue path is routed through this AsyncMock via a ``get_arq_pool``
    dependency override installed by the ``client`` fixture below.  Tests that
    assert enqueue behaviour request this fixture and inspect ``.enqueue_job``.
    """
    from unittest.mock import AsyncMock

    return AsyncMock()


# ---------------------------------------------------------------------------
# ASGI test client pointing at the real app, wired to the test session
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, arq_pool: Any
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient using the app's ASGI interface.

    The app's get_db dependency is overridden to yield the per-test session
    (which will be rolled back after the test).  get_arq_pool is overridden to
    return the shared-pool stand-in (no Redis in tests / lifespan not run).
    """
    from app.auth.deps import get_db
    from app.crypto import ensure_key
    from app.main import app
    from app.worker.arq_pool import get_arq_pool

    # Ensure key exists in the temp data dir
    ensure_key()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: arq_pool

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
