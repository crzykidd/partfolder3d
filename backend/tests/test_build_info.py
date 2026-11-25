"""Build info: GET /api/version/details + worker self-report."""

import json
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.build_info import (
    WORKER_BUILD_KEY,
    WORKER_BUILD_TTL_SECONDS,
    get_build_info,
    publish_worker_build_info,
)
from app.version import __version__


async def _login(client: AsyncClient) -> None:
    await client.post(
        "/api/setup",
        json={
            "admin_email": "admin@example.com",
            "admin_name": "Admin",
            "admin_password": "securepassword1",
        },
    )
    await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "securepassword1"},
    )


@pytest.fixture
def build_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PF3D_GIT_SHA", "a" * 40)
    monkeypatch.setenv("PF3D_BUILD_CHANNEL", "dev")
    monkeypatch.setenv("PF3D_BUILD_DATE", "2026-11-25T12:00:00Z")


def test_get_build_info_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PF3D_GIT_SHA", "PF3D_BUILD_CHANNEL", "PF3D_BUILD_DATE"):
        monkeypatch.delenv(var, raising=False)
    assert get_build_info() == {
        "version": __version__,
        "commit": "unknown",
        "channel": "local",
        "build_date": "unknown",
    }


@pytest.mark.asyncio
async def test_details_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/version/details")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_plain_version_stays_public(client: AsyncClient) -> None:
    resp = await client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": __version__}


@pytest.mark.asyncio
async def test_details_worker_present(
    client: AsyncClient, arq_pool: AsyncMock, build_env: None
) -> None:
    await _login(client)
    worker = {**get_build_info(), "started_at": "2026-11-25T11:00:00Z", "host": "w1"}
    arq_pool.get = AsyncMock(return_value=json.dumps(worker))
    resp = await client.get("/api/version/details")
    assert resp.status_code == 200
    data = resp.json()
    assert data["backend"] == {
        "version": __version__,
        "commit": "a" * 40,
        "channel": "dev",
        "build_date": "2026-11-25T12:00:00Z",
    }
    assert data["worker"] == worker
    assert data["error"] is None
    arq_pool.get.assert_awaited_once_with(WORKER_BUILD_KEY)


@pytest.mark.asyncio
async def test_details_worker_absent(client: AsyncClient, arq_pool: AsyncMock) -> None:
    await _login(client)
    arq_pool.get = AsyncMock(return_value=None)
    resp = await client.get("/api/version/details")
    assert resp.status_code == 200
    assert resp.json()["worker"] is None
    assert resp.json()["error"] is None


@pytest.mark.asyncio
async def test_details_redis_error_does_not_500(client: AsyncClient, arq_pool: AsyncMock) -> None:
    await _login(client)
    arq_pool.get = AsyncMock(side_effect=ConnectionError("redis down"))
    resp = await client.get("/api/version/details")
    assert resp.status_code == 200
    data = resp.json()
    assert data["worker"] is None
    assert data["error"]
    assert data["backend"]["version"] == __version__


@pytest.mark.asyncio
async def test_publish_worker_build_info_writes_key(build_env: None) -> None:
    redis = AsyncMock()
    await publish_worker_build_info(redis, "2026-11-25T11:00:00Z")
    redis.set.assert_awaited_once()
    args, kwargs = redis.set.call_args
    assert args[0] == WORKER_BUILD_KEY
    payload = json.loads(args[1])
    assert payload["commit"] == "a" * 40
    assert payload["channel"] == "dev"
    assert payload["started_at"] == "2026-11-25T11:00:00Z"
    assert payload["host"]
    assert kwargs["ex"] == WORKER_BUILD_TTL_SECONDS


@pytest.mark.asyncio
async def test_publish_worker_build_info_swallows_errors() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock(side_effect=ConnectionError("down"))
    await publish_worker_build_info(redis, "x")  # must not raise


@pytest.mark.asyncio
async def test_worker_startup_publishes(monkeypatch: pytest.MonkeyPatch) -> None:
    """worker.startup writes the key early (before DB seeding is reached)."""
    import worker as worker_module  # noqa: PLC0415

    redis = AsyncMock()
    ctx: dict = {"redis": redis}

    class _Stop(Exception):
        pass

    # Stop right after the build-info publish by failing the DB seed.
    import app.db as app_db  # noqa: PLC0415

    def _boom() -> None:
        raise _Stop

    monkeypatch.setattr(app_db, "SessionLocal", _boom)
    with pytest.raises(_Stop):
        await worker_module.startup(ctx)
    redis.set.assert_awaited_once()
    assert redis.set.call_args.args[0] == WORKER_BUILD_KEY
    assert ctx["build_started_at"]
