#!/usr/bin/env bash
#
# verify-backend.sh — canonical backend verify recipe for PartFolder 3D.
#
# Encodes the full backend gate ONCE so it stops being re-pasted into every
# handoff prompt. Steps:
#   1. Ensure an ephemeral Postgres (container `pf3d-pg-v` on host :5433).
#   2. Pinned lint — backend/.venv/bin/ruff 0.8.4 + backend/pyproject.toml.
#   3. alembic upgrade head against that DB.
#   4. pytest -n auto (xdist REQUIRED — see gotcha below).
#
# GOTCHA (xdist): pytest MUST run with `-n auto`. Under xdist each worker
# drops+recreates its OWN per-worker DB and migrates it fresh. A SERIAL run
# reuses the single base DB, so committed rows accumulate across tests and
# produce spurious count-assertion failures. Always parallel.
#
# GOTCHA (pinned ruff): use backend/.venv/bin/ruff, NOT an unpinned system
# ruff. An unpinned/no-config ruff reports false UP042/F841 that CI (pinned
# 0.8.4) does not.
#
# The container is LEFT RUNNING on success for fast reuse. Pass --teardown to
# stop+remove it afterward.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
PG_CONTAINER="pf3d-pg-v"
PG_PORT="5433"
export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:${PG_PORT}/partfolder3d"

TEARDOWN=0
for arg in "$@"; do
  case "$arg" in
    --teardown|--no-keep) TEARDOWN=1 ;;
    *) echo "unknown arg: $arg (accepts: --teardown)"; exit 2 ;;
  esac
done

echo "==> [1/4] Ensuring ephemeral Postgres container '${PG_CONTAINER}' on :${PG_PORT}"
if docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
  echo "    container exists — starting it (reuse)"
  docker start "$PG_CONTAINER" >/dev/null
else
  echo "    container absent — creating it"
  docker run -d --name "$PG_CONTAINER" \
    -e POSTGRES_USER=partfolder3d \
    -e POSTGRES_PASSWORD=testpass \
    -e POSTGRES_DB=partfolder3d \
    -p "${PG_PORT}:5432" \
    postgres:16-alpine >/dev/null
fi

echo "    waiting for Postgres to accept connections..."
for i in $(seq 1 30); do
  if docker exec "$PG_CONTAINER" pg_isready -U partfolder3d -d partfolder3d >/dev/null 2>&1; then
    echo "    Postgres ready"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "ERROR: Postgres did not become ready in time" >&2
    exit 1
  fi
  sleep 1
done

echo "==> [2/4] Lint (pinned ruff 0.8.4 + backend/pyproject.toml)"
"$BACKEND_DIR/.venv/bin/ruff" check "$BACKEND_DIR"

echo "==> [3/4] alembic upgrade head"
( cd "$BACKEND_DIR" && ./.venv/bin/alembic upgrade head )

echo "==> [4/4] pytest -n auto (xdist — fresh per-worker DB; REQUIRED)"
( cd "$BACKEND_DIR" && ./.venv/bin/pytest -n auto )

if [ "$TEARDOWN" -eq 1 ]; then
  echo "==> tearing down '${PG_CONTAINER}' (--teardown)"
  docker stop "$PG_CONTAINER" >/dev/null
  docker rm "$PG_CONTAINER" >/dev/null
else
  echo "==> done. Container '${PG_CONTAINER}' left running for reuse (pass --teardown to remove)."
fi

echo "backend verify: OK"
