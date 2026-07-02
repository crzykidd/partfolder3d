---
name: 2026-07-02-production-images-nginx-frontend
status: done
created: 2026-07-02
model: sonnet
completed: 2026-07-02
result: >
  Created nginx/Dockerfile (bakes config + logos, nginx -t via sed-stub workaround for
  BuildKit /etc/hosts read-only). Added /img/ location to nginx/nginx.conf. Converted
  publish.yml to 3-image matrix (backend/frontend/nginx) with per-image GHA cache scopes.
  Updated docker-compose.yml nginx service to use partfolder3d-nginx:latest, removed
  bind-mounts, added optional override comment. Updated README with baked-config docs +
  override tip. Added Step 6b to release-prep.md for nginx-config-changed callout.
  Updated CHANGELOG.md [Unreleased] and docs/decisions.md. Nginx image build + nginx -T
  verification passed. Both compose validations passed. Frontend prod build FAILED with
  pre-existing TypeScript errors on dev (verified pre-existing before this task's changes).
---

# Task: Make the image-based production deploy self-contained (publish frontend + nginx images, bake nginx config)

The production `docker-compose.yml` is meant to be "pull published images + `.env`, `docker
compose up`" — but two things break that today:
1. **The frontend image is never published.** `publish.yml` builds ONLY the backend
   (`ghcr.io/crzykidd/partfolder3d`, context `.`). Nothing builds
   `ghcr.io/crzykidd/partfolder3d-frontend` (compose references it → pull fails / 404).
2. **nginx runs stock `nginx:1.27-alpine` with its config bind-mounted from `./nginx/nginx.conf`
   (+ `./docs/images`).** A pull-images-only host has no such files → nginx falls back to its
   built-in default → no `/api/` proxy (API 404s), no SPA fallback (deep links/refresh break),
   1 MB upload cap (model uploads 413). It also lets the running config drift from the versioned
   images across updates.

Fix both so a fresh host needs **zero repo files** beyond `docker-compose.yml` + `.env`.

## Before you start

- Read `docs/decisions.md` (top entries) + `prompts/startnewsession.md` (CI workflow shape,
  verify discipline). **The `ci.yml` job names are load-bearing required-check contexts — do not
  rename them.** This task doesn't touch `ci.yml`.
- Current state to build on:
  - `.github/workflows/publish.yml` — single `build-push` job, `images:
    ghcr.io/crzykidd/partfolder3d`, `context: .` (root `Dockerfile` = backend/worker). Triggers:
    push `[dev, main]` + release. Tag scheme (dev/sha/latest/semver/major) must be preserved.
  - `frontend/Dockerfile` — multistage; **`prod` target** copies built assets to `/dist` (the
    `frontend_dist` volume) and exits. The frontend compose service runs this once.
  - `nginx/nginx.conf` — CORRECT already (`client_max_body_size 1024m`, `location /api/` proxy,
    `try_files … /index.html` SPA fallback, `/health`). Logos currently served because
    `./docs/images` is bind-mounted at `/usr/share/nginx/html/img`.
  - `docker-compose.yml` nginx service (~line 143): `image: nginx:1.27-alpine`, bind-mounts
    `./nginx/nginx.conf` + `./docs/images`, serves `frontend_dist` at `/usr/share/nginx/html`.
  - `docker-compose.dev.yml` — dev builds from source, nginx bind-mounts `nginx.dev.conf`
    (proxies to the Vite dev server). **Leave dev working** (dev clones the repo; the fragility
    is production-only). Dev may keep its bind-mounts.

## What to do

1. **New `nginx/Dockerfile`** — `FROM nginx:1.27-alpine`; `COPY nginx/nginx.conf
   /etc/nginx/conf.d/default.conf`; bake the logo images to a path OUTSIDE the `frontend_dist`
   volume mount (e.g. `COPY docs/images/ /usr/share/nginx/img/`). Keep the SPA served from
   `/usr/share/nginx/html` (still the `frontend_dist` volume at runtime). Run `nginx -t` in the
   build to fail fast on a bad config.
2. **Update `nginx/nginx.conf`** — add an explicit `location /img/ { alias /usr/share/nginx/img/;
   }` so logos serve from the baked path (they're no longer under the html/volume root). Don't
   change the `/api/`, `/health`, SPA-fallback, or `client_max_body_size` behavior.
3. **`publish.yml` → build & push ALL THREE images.** Convert the single job to a **matrix**
   over: backend (`ghcr.io/crzykidd/partfolder3d`, context `.`, root Dockerfile), frontend
   (`ghcr.io/crzykidd/partfolder3d-frontend`, context `./frontend`, `target: prod`), nginx
   (`ghcr.io/crzykidd/partfolder3d-nginx`, context `.`, `file: nginx/Dockerfile`). Each matrix
   entry runs `docker/metadata-action` with its own `images:` + the SAME tag scheme
   (dev/sha/latest/semver/major) and `build-push-action`. Preserve triggers, permissions, gha
   cache.
4. **`docker-compose.yml` (prod)** — nginx service now uses
   `image: ghcr.io/crzykidd/partfolder3d-nginx:latest` (with the `:0.x` pin comment like the
   others). **Remove the required `./nginx/nginx.conf` and `./docs/images` bind-mounts** (config
   + logos are baked). Keep the `frontend_dist` volume mount. Add a **commented, optional**
   override so operators can still supply a custom config, e.g.:
   `# - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro  # optional: override baked config`.
5. **README** — in the Docker/deploy config section: state that the nginx config is **baked into
   the `partfolder3d-nginx` image** (sane defaults, works out of the box), show how to **override
   it with a custom config** (uncomment the bind-mount → your own `default.conf`), and note that
   the baked default is the supported path.
6. **Release-process rule** — add to `.claude/commands/release-prep.md` a step: when preparing a
   release, check whether `nginx/nginx.conf` changed since the previous release tag; if so, add a
   prominent **"⚠️ nginx config changed"** callout to the release notes so operators running a
   custom/overridden config reconcile their copy. Also add a one-line note to the README override
   section pointing operators to watch release notes for config changes.

## Conventions to honor

- **Changelog:** `CHANGELOG.md [Unreleased]` — Added: published frontend + nginx images; Changed:
  nginx config baked into image, production compose no longer needs host bind-mounts.
- **Verify (must actually build):**
  - `docker build -f nginx/Dockerfile -t pf3d-nginx-test .` succeeds (incl. the `nginx -t`), then
    run it and confirm the config is present + `/img/` alias resolves
    (`docker run --rm pf3d-nginx-test nginx -T | grep -E 'proxy_pass|client_max_body_size|/img/'`).
  - `docker build -f frontend/Dockerfile --target prod -t pf3d-frontend-test ./frontend` succeeds.
  - `docker compose config --quiet` AND `docker compose -f docker-compose.dev.yml config --quiet`
    both pass. Clean up throwaway images.
  - Validate `publish.yml` is valid YAML with the 3-way matrix + correct image names/contexts.
  - Note: the matrix actually pushing 3 images is CI-verified on merge (not pushable locally) —
    flag that in your report.

## When done

1. Frontmatter (`status`/`completed`/`result`), then `git mv` into `prompts/done/` or
   `prompts/failed/`.
2. Record non-obvious decisions in `docs/decisions.md` (the frontend-image gap, the baked-nginx
   design + logo `/img/` alias, the release-note-callout rule).
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run the build verifications, and
   report back: paths to stage, a one-line conventional-commit message, and verification output.
   The orchestrator commits on `dev`. Never `git add -A`.
