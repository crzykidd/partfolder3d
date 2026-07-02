#!/bin/sh
# PartFolder 3D container entrypoint.
#
# Bundles DB migrations into normal service startup so there is NO separate
# one-shot container (which would show as "exited" in docker ps / Portainer and
# read as a broken stack). The service that sets RUN_MIGRATIONS=true applies
# `alembic upgrade head` before its main process starts; every other service
# (e.g. the worker) skips migrations and waits for the migrating service to be
# healthy via compose depends_on.
#
# Every startup phase logs and FAILS LOUDLY — a service that can't start must
# say why (bad DB creds/host, unwritable volume, blocked migration), never hang
# silently. Tuning knobs (all optional):
#   DB_WAIT_TIMEOUT (s, default 90)       how long to wait for the DB to accept connections
#   DB_CONNECT_TIMEOUT (s, default 5)     per-attempt connect timeout (app.dbcheck)
#   MIGRATION_LOCK_TIMEOUT_MS (30000)     max wait for a migration lock before erroring
#   MIGRATION_STATEMENT_TIMEOUT_MS (300000) max runtime for a single migration statement
set -e

log() { echo "[entrypoint] $*"; }
fatal() { echo "[entrypoint] FATAL: $*" >&2; exit 1; }

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    log "starting migration bootstrap as uid=$(id -u) gid=$(id -g)"

    # --- 1. Data-dir writability (catches PUID/PGID + volume-ownership problems) ---
    DATA_DIR="${DATA_DIR:-/data}"
    if ! { mkdir -p "$DATA_DIR" && touch "$DATA_DIR/.perm-check"; } 2>/dev/null; then
        fatal "DATA_DIR '$DATA_DIR' is not writable by uid=$(id -u) gid=$(id -g). \
The mounted volume/host path must be owned by (or writable to) PUID:PGID — see .env."
    fi
    rm -f "$DATA_DIR/.perm-check" 2>/dev/null || true
    log "DATA_DIR '$DATA_DIR' is writable."

    # --- 2. Wait for the database, logging the REAL error each attempt ---
    db_timeout="${DB_WAIT_TIMEOUT:-90}"
    waited=0
    log "waiting for database (up to ${db_timeout}s)..."
    until python -m app.dbcheck 2>/tmp/dbcheck.err; do
        if [ "$waited" -ge "$db_timeout" ]; then
            log "database still unreachable after ${db_timeout}s — last error:"
            sed 's/^/[entrypoint][db] /' /tmp/dbcheck.err >&2 2>/dev/null || cat /tmp/dbcheck.err >&2
            fatal "cannot reach the database. Check DATABASE_URL, the db service, and credentials \
(note: a reused Postgres volume keeps its ORIGINAL password even if you changed it in .env)."
        fi
        log "  db not ready: $(tr '\n' ' ' < /tmp/dbcheck.err | cut -c1-200)"
        waited=$((waited + 3))
        sleep 3
    done
    log "database is reachable."

    # --- 3. Migrate. PYTHONUNBUFFERED streams alembic's per-migration output live
    #        (otherwise it block-buffers and a hang shows NOTHING). `timeout` is a
    #        hard backstop so this step can never hang forever — it fails with a
    #        clear message naming the last migration. env.py also bounds lock/
    #        statement time so a lock-blocked migration errors on its own in ~30s. ---
    export PYTHONUNBUFFERED=1
    mig_timeout="${MIGRATION_TIMEOUT:-600}"
    log "current database revision (before upgrade):"
    timeout 30 alembic current || log "  (could not read current revision within 30s — see above)"
    log "applying database migrations (alembic upgrade head, hard timeout ${mig_timeout}s)..."
    if timeout "$mig_timeout" alembic upgrade head; then
        log "migrations up to date."
    else
        rc=$?
        if [ "$rc" = "124" ]; then
            fatal "migrations TIMED OUT after ${mig_timeout}s — a migration is stuck (most likely blocked \
on a database lock, or a very slow statement). The last 'Running upgrade …' line above names the culprit."
        fi
        fatal "'alembic upgrade head' failed with exit code ${rc} — see the alembic output above."
    fi
fi

log "starting: $*"
exec "$@"
