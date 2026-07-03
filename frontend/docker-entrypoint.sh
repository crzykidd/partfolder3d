#!/bin/sh
# PartFolder 3D frontend "publish" container.
#
# This is a one-shot job: it copies the pre-built static assets into the shared
# `frontend_dist` volume that nginx serves, then exits 0. nginx waits for it via
# `depends_on: condition: service_completed_successfully`. It logs a version
# banner and FAILS LOUDLY (clear message + non-zero exit) so a silent exit can
# never block the stack without explanation.
set -e

log() { echo "[frontend] $*"; }
fatal() { echo "[frontend] FATAL: $*" >&2; exit 1; }

version="$(node -p "require('/app/package.json').version" 2>/dev/null || echo unknown)"
log "PartFolder 3D frontend v${version} — uid=$(id -u) gid=$(id -g)"

DEST="${DIST_DIR:-/dist}"

# Writability preflight — a PUID/PGID or reused-volume ownership mismatch shows
# up here as a clear message instead of an opaque non-zero exit.
if ! { mkdir -p "$DEST" && touch "$DEST/.perm-check"; } 2>/dev/null; then
    fatal "'$DEST' (the frontend_dist volume) is not writable by uid=$(id -u) gid=$(id -g). \
It must be owned by (or writable to) PUID:PGID — see .env. If you changed PUID/PGID, recreate \
the volume: 'docker compose down -v' (wipes data) or chown the volume to that UID:GID."
fi
rm -f "$DEST/.perm-check" 2>/dev/null || true

log "publishing built assets to '$DEST'..."
if cp -rp /app/dist/. "$DEST"/ 2>/tmp/cp.err; then
    count="$(find "$DEST" -type f 2>/dev/null | wc -l | tr -d ' ')"
    log "published ${count} files to '$DEST' — frontend ready. Exiting 0 (this is expected)."
else
    log "copy failed:"
    sed 's/^/[frontend] /' /tmp/cp.err >&2 2>/dev/null || cat /tmp/cp.err >&2
    fatal "failed to copy built assets from /app/dist to '$DEST' (see error above)."
fi
