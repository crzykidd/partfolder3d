#!/bin/sh
# PartFolder 3D container entrypoint.
#
# Bundles DB migrations into normal service startup so there is NO separate
# one-shot container (which would show as "exited" in docker ps / Portainer and
# read as a broken stack). The service that sets RUN_MIGRATIONS=true applies
# `alembic upgrade head` before its main process starts; every other service
# (e.g. the worker) skips migrations and waits for the migrating service to be
# healthy via compose depends_on.
set -e

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "[entrypoint] applying database migrations (alembic upgrade head)..."
  alembic upgrade head
  echo "[entrypoint] migrations up to date."
fi

exec "$@"
