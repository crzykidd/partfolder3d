"""Standalone database-reachability probe for the container entrypoint.

Run as ``python -m app.dbcheck``. Exits 0 if the database accepts a connection,
non-zero otherwise — and prints the ACTUAL error (auth failure, host
unreachable, connection refused, timeout) to stderr. The entrypoint loops on
this so a start-up that can't reach the DB produces a clear, repeated log line
instead of a silent hang.

Exit codes: 0 = connected, 1 = connection failed (error printed), 2 = misconfig.
"""

import asyncio
import os
import sys


async def _check() -> None:
    import asyncpg  # imported here so the module fails loudly if the dep is missing

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)

    # asyncpg wants a plain libpq DSN, not the SQLAlchemy '+asyncpg' variant.
    dsn = url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")
    timeout = float(os.environ.get("DB_CONNECT_TIMEOUT", "5"))

    conn = await asyncpg.connect(dsn=dsn, timeout=timeout)
    try:
        await conn.execute("SELECT 1")
    finally:
        await conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(_check())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — we want to surface ANY failure verbatim
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
