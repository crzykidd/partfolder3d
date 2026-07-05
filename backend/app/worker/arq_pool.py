"""Shared arq Redis connection pool + JSON job (de)serialization.

Why this module exists
----------------------
1. **One pool per process.**  Historically every router/service that needed to
   enqueue a job called ``arq.create_pool(...)`` per request and ``aclose()``d
   it afterwards — a fresh TCP pool each time, and if ``enqueue_job`` raised the
   ``aclose`` never ran (a connection leak, ~32 sites).  The API now creates a
   single pool at app lifespan (``app.state.arq_pool``) and injects it into
   routers/services via :func:`get_arq_pool`.

2. **JSON job bodies, not pickle.**  arq defaults to ``pickle.loads`` for job
   bodies, which turns any Redis-write primitive into arbitrary code execution
   in the worker.  All job args in this app are ints/strings, so JSON is a safe
   swap.  The (de)serializer MUST be set identically on BOTH ends — the
   enqueue-side pool built here AND the worker's ``WorkerSettings`` — or jobs
   will fail to deserialize.

Deploy note: pickled jobs already sitting in the Redis queue at the moment of
this upgrade will fail to deserialize under JSON.  Drain the worker queue across
this upgrade (jobs here are short-lived and the queue is normally empty).
"""

from __future__ import annotations

import json
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import Request

from ..config import settings


def job_serializer(job: dict[str, Any]) -> bytes:
    """Serialize an arq job body to JSON bytes (replaces the pickle default)."""
    return json.dumps(job).encode("utf-8")


def job_deserializer(raw: bytes) -> dict[str, Any]:
    """Deserialize an arq job body from JSON bytes (replaces the pickle default)."""
    return json.loads(raw)


def redis_settings() -> RedisSettings:
    """Parse the configured REDIS_URL into arq RedisSettings."""
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def create_arq_pool() -> ArqRedis:
    """Create an arq Redis pool wired to the JSON (de)serializer.

    Used once at app lifespan for the shared API pool, and by the few worker
    tasks that enqueue follow-up jobs outside a live arq worker context.
    """
    return await create_pool(
        redis_settings(),
        job_serializer=job_serializer,
        job_deserializer=job_deserializer,
    )


def get_arq_pool(request: Request) -> ArqRedis:
    """FastAPI dependency: return the process-wide arq pool from ``app.state``.

    The pool is created once at lifespan startup (see ``app.main.lifespan``) and
    reused for every enqueue — no per-request pool creation, no leak.
    """
    return request.app.state.arq_pool
