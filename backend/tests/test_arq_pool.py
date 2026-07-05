"""Shared arq pool: lifespan creation/reuse + JSON job (de)serialization.

Covers app.worker.arq_pool + the app.main lifespan wiring introduced when the
~32 per-request ``create_pool``/``aclose`` sites were consolidated into a single
process-wide pool injected via ``get_arq_pool``.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.worker.arq_pool import (
    get_arq_pool,
    job_deserializer,
    job_serializer,
)


def test_get_arq_pool_returns_shared_state_pool() -> None:
    """get_arq_pool hands back exactly the pool stored on app.state — no new pool."""
    sentinel = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=sentinel)))
    assert get_arq_pool(request) is sentinel  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_lifespan_creates_pool_once_and_closes_it() -> None:
    """The lifespan creates ONE arq pool, stores it on app.state, and closes it once.

    create_arq_pool is patched so no real Redis is contacted; entering and
    exiting the lifespan context must create the pool exactly once and aclose it
    exactly once on shutdown.  Reuse is proven by get_arq_pool returning that
    same instance for every request.
    """
    from app.main import app, lifespan

    fake_pool = AsyncMock()

    # create_arq_pool is imported inside the lifespan body from app.worker.arq_pool.
    with patch(
        "app.worker.arq_pool.create_arq_pool", AsyncMock(return_value=fake_pool)
    ) as mk:
        async with lifespan(app):
            # Created exactly once and reachable via the dependency.
            assert mk.await_count == 1
            assert app.state.arq_pool is fake_pool
            req = SimpleNamespace(app=app)
            assert get_arq_pool(req) is fake_pool  # type: ignore[arg-type]
            # A second dependency resolution returns the SAME pool (reused).
            assert get_arq_pool(req) is fake_pool  # type: ignore[arg-type]
            assert mk.await_count == 1  # still only created once

    # Closed exactly once on shutdown.
    fake_pool.aclose.assert_awaited_once()


def test_json_serializer_round_trips_a_job_body() -> None:
    """A representative arq job body (ints/strings only) round-trips through JSON.

    arq stores args as a tuple; JSON restores it as a list, which unpacks the
    same way via ``*args`` on the worker.
    """
    body = {
        "t": 1,
        "f": "render_item",
        "a": (77,),
        "k": {"retry_of_job_id": "5"},
        "et": 1234567890,
    }
    restored = job_deserializer(job_serializer(body))
    assert restored == {
        "t": 1,
        "f": "render_item",
        "a": [77],
        "k": {"retry_of_job_id": "5"},
        "et": 1234567890,
    }
