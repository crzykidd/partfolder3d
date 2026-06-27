"""PartFolder 3D — arq worker entry point.

Phase 0: empty task set. Connects to Redis and idles.
Background jobs (scan, render, import) are added in Phase 4+.
"""

import asyncio
import os

from arq.connections import RedisSettings


def get_redis_settings() -> RedisSettings:
    """Parse REDIS_URL into arq RedisSettings."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    # arq RedisSettings.from_dsn parses redis:// URLs
    return RedisSettings.from_dsn(url)


class WorkerSettings:
    """arq worker configuration.

    Add task functions to `functions` list as they are implemented.
    """

    functions: list = []  # empty in Phase 0
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 300  # 5 minutes default timeout


async def main() -> None:
    """Run the worker (used when executing this file directly)."""
    from arq import Worker

    worker = Worker(WorkerSettings)  # type: ignore[arg-type]
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(main())
