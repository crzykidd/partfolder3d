---
name: 2026-11-25-frontend-npm-update-alpine-prod
status: done             # pending | in-progress | done | failed
created: 2026-11-25
model: sonnet
completed: 2026-11-25
result: npm update done (12->3 vulns); frontend prod stage alpine-only, 821MB->15MB, trivy 0/0
---

# Task: npm in-range updates, then alpine-only frontend prod image stage

Implements audit Tasks **5 then 4** from `docs/security-audit-2026-11-25.md` (read §3.3 npm part,
§4.4, §5 Tasks 4–5). Do them **in that order** so the image build in step B uses the updated lockfile.

## Before you start

- Read `CLAUDE.md`, the audit sections, `frontend/Dockerfile`, `frontend/docker-entrypoint.sh`,
  `frontend/package.json`, the frontend/nginx services in `docker-compose.yml` and
  `docker-compose.dev.yml`, `nginx/Dockerfile` (how nginx gets the dist volume), and the image
  build jobs in `.github/workflows/` (target names for the frontend image).
- **Don't touch `backend/`, root `Dockerfile`, `.github/workflows/ci.yml`/`dev-checks.yml` python bits,
  or `docs/decisions.md` beyond adding your own entry** — a concurrent backend agent edits those.
  Don't edit `CHANGELOG.md`.
- **Do NOT touch the running dev stack** (`partfolder3d-*-1`) — the owner's vite dev server runs from
  this repo's `frontend/`. `npm update` changes `node_modules` in place; that's acceptable (the dev
  container has its own node_modules in the image), but don't restart anything.
- The `dev` Dockerfile target must keep working unchanged.

## Working tree check

`git status --porcelain`; stop and report if a file you need is dirty. Unrelated dirty files: note once.

## A. npm in-range update (audit Task 5)

1. `cd frontend && npm audit` (record the baseline: expect 2 crit / 7 high / 3 moderate).
2. `npm update` (in-range only — **no** `npm audit fix --force`, no major bumps). If the audit doc lists
   specific targets (vite 6.4.4, react-router 7.18.2, postcss, nanoid, browserslist, source-map-js),
   confirm they landed. Only raise floors in `package.json` if needed to force a patched version.
3. `npm audit` again — expect only the vitest pair remaining (that's audit Task 6, out of scope).
4. Gate you may run: `npx tsc -b --force && npx vite build && npx vitest run --no-file-parallelism`
   (the host is loaded; if timeouts flake in heavy async files, re-run those files alone and report).

## B. Alpine-only prod stage (audit Task 4)

1. `frontend/Dockerfile`: keep `deps`/`builder`/`dev` as-is (optionally bump builder base to
   `node:24-alpine` **only if** the audit recommends it and the build passes — otherwise keep 22).
   Change `prod` to `FROM alpine:<current stable, audit says 3.24>` with `COPY --from=builder /app/dist ...`,
   the entrypoint, and whatever the entrypoint reads. Preserve the `/dist` 0777 behavior and CMD contract.
2. `frontend/docker-entrypoint.sh`: remove the `node -p` dependency for the version banner — write a
   `VERSION` file in the builder stage (from package.json) and read it, or parse package.json with
   `sed`/`grep`. POSIX sh only (alpine busybox). Keep the loud-error behavior.
3. **Smoke test**: `docker build --target prod -t pf3d-smoke-frontend:alpine frontend/`; run it with a
   throwaway named volume mounted at the same path compose uses
   (`docker run --rm -v pf3d-smoke-dist:<path> pf3d-smoke-frontend:alpine`), check exit 0, the version
   banner prints the real version, and the volume has `index.html` + assets (inspect via a throwaway
   `alpine` container). Optionally serve it with `nginx:1.30-alpine` on a random high port and `curl` index.html.
   Report image size before/after (`docker images`). Trivy it
   (`docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --severity CRITICAL,HIGH pf3d-smoke-frontend:alpine`).
   Clean up: remove `pf3d-smoke-*` images, containers and the `pf3d-smoke-dist` volume.
4. Add a short entry to `docs/decisions.md` (newest at top) for the alpine-only prod stage + version-file
   approach. Note the change in `docs/architecture.md` only if it documents the frontend image layout.

## When done

1. Frontmatter; move this file (plain `mv`, it's untracked) to `prompts/done/` or `prompts/failed/`.
2. Do **not** commit. Report: files changed, npm audit before/after, notable version changes, gate
   results, smoke-test + size + trivy results.
