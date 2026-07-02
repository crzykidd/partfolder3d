---
name: 2026-07-01-docker-runtime-uid
status: done
created: 2026-07-01
model: sonnet
completed: 2026-07-02
result: >
  All changes applied and verified. Backend image built and ran as UID 1234:1234 —
  confirmed `id` output, DATA_WRITE_OK, and IMPORT_OK. Both docker compose config
  validations exit 0. Seven files changed: Dockerfile, frontend/Dockerfile,
  docker-compose.yml, docker-compose.dev.yml, .env.example, CHANGELOG.md,
  docs/decisions.md.
---

# Task: Configurable runtime UID/GID (PUID/PGID) for the images we control (NFS mapping)

The maintainer runs the library storage on **NFS** and needs the containers that write to it to
run as a specific UID:GID so files land with the right ownership. Add a **`PUID`/`PGID`** setting
that sets the runtime user on the images this project builds — **backend and worker are the
critical ones** (they write item dirs, sidecars, images, renders, thumbs, and extracted ZIPs to
the library mount and to `/data`); also apply to the frontend image for consistency. Do NOT try
to set a user on the third-party images (postgres/redis/nginx) — they manage their own users.

## Context you must know

- Root `Dockerfile` builds the **backend+worker** image (worker overrides CMD to
  `python worker.py`). It runs as **root today** (no `USER`), `WORKDIR /app`,
  `ENTRYPOINT /app/docker-entrypoint.sh`, and `RUN mkdir -p /data`. `PYTHONDONTWRITEBYTECODE=1`
  is already set (no `__pycache__` writes).
- `backend/docker-entrypoint.sh` runs `alembic upgrade head` when `RUN_MIGRATIONS=true`, then
  `exec "$@"`. It must keep working when the container runs as a non-root UID (migrations only
  need DB network access — fine).
- `frontend/Dockerfile` — inspect it; determine what it writes at runtime (e.g. nginx serving a
  built `dist`, or copying dist into a shared volume) and whether a non-root user needs any dir
  writable.
- Compose: `docker-compose.yml` (production, image-based) and `docker-compose.dev.yml` (dev,
  build-from-source, bind-mounts). `.env.example` is the env template.
- Writable runtime paths: the **library mount** (operator-provided; for NFS it's owned by the
  target UID — not the image's concern) and **`/data`** (config, `secret.key`, trash, backups —
  a named volume in prod).

## What to do

1. **Make the backend/worker image run cleanly as an arbitrary non-root UID:**
   - `Dockerfile`: make `/data` world-writable so a **named volume** inherits open perms and any
     UID can write it (`RUN mkdir -p /data && chmod 0777 /data`). Set `ENV HOME=/tmp` (and
     `XDG_CACHE_HOME=/tmp`) so libraries that write to `$HOME` don't fail for a UID with no
     passwd entry. Do NOT add a hardcoded `USER` — the UID is chosen at runtime via compose.
   - Confirm nothing else writes outside `/data`, `/tmp`, or the (operator-owned) library mount
     at runtime.
2. **PUID/PGID wiring:**
   - `.env.example`: add `PUID=1000` and `PGID=1000` with a comment explaining they set the
     runtime user for NFS ownership, and that mounted volumes/library paths must be owned by that
     UID:GID.
   - `docker-compose.yml` (prod): add `user: "${PUID:-1000}:${PGID:-1000}"` to **backend**,
     **worker**, and **frontend** services. Keep everything else intact.
   - `docker-compose.dev.yml`: apply the same `user:` to backend/worker/frontend **only if** it
     won't break the local bind-mount/hot-reload dev flow (dev bind-mounts `./private_data/data`
     owned by the host user, and the frontend uses a root-owned `node_modules` volume). If it
     risks breaking dev, add the `user:` line **commented** with a one-line note instead of
     enabling it. Use your judgment; explain the choice in your report + decisions.md.
3. **frontend image:** ensure it runs as a non-root UID (make any runtime-written dir, e.g. the
   dist/output or nginx temp/cache/pid paths, writable — mirror the `/data` chmod approach). If
   the prod frontend is pure static output to a shared volume, make that path world-writable in
   its Dockerfile.

## Conventions to honor

- **Changelog:** `[Unreleased]` entry (Added: configurable `PUID`/`PGID` runtime user for
  NFS-friendly file ownership on the backend/worker/frontend images). Note in the entry that
  operators upgrading should ensure their library mount + `/data` volume are owned by PUID:PGID.
- **Verify (must actually build + run):**
  - Build the backend image: `docker build -t pf3d-uid-test .` (from repo root).
  - Run it as a non-root UID with a fresh named volume and confirm it starts + can write `/data`:
    e.g. `docker run --rm --user 1234:1234 -e HOME=/tmp -v pf3d_uidtest_data:/data
    --entrypoint sh pf3d-uid-test -c 'id; touch /data/probe && echo DATA_WRITE_OK && python -c "import app.main"'`.
    Clean up the throwaway volume/image afterward.
  - `docker compose config --quiet` and `docker compose -f docker-compose.dev.yml config --quiet`
    both pass with the new `user:` lines and a sample `PUID`/`PGID`.
  - Report the actual command output proving it ran as the custom UID and wrote to `/data`.

## When done

1. Frontmatter (`status`/`completed`/`result`), then `git mv` into `prompts/done/` or
   `prompts/failed/`.
2. Record non-obvious decisions in `docs/decisions.md` (esp. the dev-compose choice and the
   /data-chmod-for-named-volumes rationale).
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run the build+run verification, and
   report back: paths to stage, a one-line conventional-commit message, and the verification
   output. The orchestrator commits on the current feature branch. Never `git add -A`.
