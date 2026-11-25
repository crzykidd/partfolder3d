"""Build info stamped into the image at build time (CI passes build-args -> ENV).

Shape everywhere: {version, commit (full sha), channel, build_date (ISO-8601 UTC)}.
Local builds default to channel ``local`` and commit/build_date ``unknown``.
"""

import os
import socket
from datetime import UTC, datetime
from typing import Any

from .version import __version__

WORKER_BUILD_KEY = "pf3d:build:worker"
# Worker refreshes the key every minute; the TTL tolerates a few missed beats.
WORKER_BUILD_TTL_SECONDS = 180


def get_build_info() -> dict[str, str]:
    """Return this process's build info from the PF3D_* env vars."""
    return {
        "version": __version__,
        "commit": os.environ.get("PF3D_GIT_SHA") or "unknown",
        "channel": os.environ.get("PF3D_BUILD_CHANNEL") or "local",
        "build_date": os.environ.get("PF3D_BUILD_DATE") or "unknown",
    }


def get_worker_build_payload(started_at: str) -> dict[str, Any]:
    """Build info + started_at + hostname, as the worker self-reports it."""
    return {**get_build_info(), "started_at": started_at, "host": socket.gethostname()}


def utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def publish_worker_build_info(redis: Any, started_at: str) -> None:
    """Write the worker's build info to Redis with a TTL (best-effort, never raises)."""
    import json  # noqa: PLC0415
    import logging  # noqa: PLC0415

    try:
        await redis.set(
            WORKER_BUILD_KEY,
            json.dumps(get_worker_build_payload(started_at)),
            ex=WORKER_BUILD_TTL_SECONDS,
        )
    except Exception:
        logging.getLogger(__name__).warning("could not publish worker build info", exc_info=True)
