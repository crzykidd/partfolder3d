---
name: 2026-06-27-ci-workflows
status: completed        # pending | completed | failed
created: 2026-06-27
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-06-27
result: authored four tolerant-bootstrap CI workflows (ci.yml, codeql.yml, publish.yml, retention.yml) modeled on filament-bridge; updated standards.md and docs/decisions.md
---

# Task: Add filament-bridge-style CI workflows (tolerant bootstrap)

Author four GitHub Actions workflows for `partfolder3d`, modeled directly on the
`filament-bridge` project's proven implementation of the `code-checkin-and-pr` standard,
tailored to PartFolder 3D's planned stack and made **tolerant of the not-yet-existing
app code** so they pass cleanly on the current empty repo and auto-enforce as scaffolding
lands.

## Before you start

- **Read the reference workflows verbatim** — they are the style to copy:
  - `/home/manderse/projects/filament-bridge/.github/workflows/ci.yml`
  - `/home/manderse/projects/filament-bridge/.github/workflows/codeql.yml`
  - `/home/manderse/projects/filament-bridge/.github/workflows/publish.yml`
  - `/home/manderse/projects/filament-bridge/.github/workflows/retention.yml`
  - **Preserve their hard-won trigger comments** (push-only CI to avoid duplicate/stuck
    required checks; CodeQL gating on `main` PR + push, not `dev`; image-build job always
    runs but only builds on PR). These comments explain real bugs — keep them, adapted.
- Read this repo's `CLAUDE.md` and `standards.md`. This repo adopts `code-checkin-and-pr`
  @ 1.2.0: **work on `dev`** (you are already on `dev`), **conventional commit prefixes**,
  **no `Co-authored-by:` trailers**, **never `--no-verify`**.
- Read `PRD.md` §3 for the stack: Python/FastAPI backend, React/TypeScript/Vite frontend,
  PostgreSQL + alembic migrations, pytest, Docker, nginx, GHCR image
  `ghcr.io/crzykidd/partfolder3d`.

## Working tree check

Run `git status --porcelain`. Only this prompt file and the new `.github/workflows/*`
files plus `standards.md` / `docs/decisions.md` should be touched. If anything else is
dirty and overlaps, list it and stop.

## Stack mapping (filament-bridge → partfolder3d)

| filament-bridge | partfolder3d |
|---|---|
| backend Python 3.12 + `ruff check backend/` | same |
| frontend `npm ci` + `npx tsc --noEmit` (Node 22) | same (`frontend/`) |
| alembic migrations in `backend/` | same (env vars become `DATABASE_URL`, `DATA_DIR`) |
| `pytest` in `backend/` | same |
| `docker-compose.yml`, `docker-compose.dev.yml` | same names |
| image `ghcr.io/crzykidd/filament-bridge` | `ghcr.io/crzykidd/partfolder3d` |
| CodeQL `[python, javascript-typescript]` | same |
| retention package name `filament-bridge` | `partfolder3d` |

## What to do

Create `.github/workflows/` with four files mirroring the reference, with these changes:

1. **`ci.yml`** — `on: push: branches: [dev, main]` (keep the push-only comment). Jobs:
   `lint`, `config-validate`, `migration-check`, `compose-validate`, `image-build`,
   `test` — same names/structure as filament-bridge. **Make each job tolerant:** every job
   must still RUN (never job-level `if:`-skipped, so its required-check context always
   reports), but guard the real commands behind an existence check so an empty repo
   passes. Concretely:
   - `lint`: `if [ -d backend ]; then pip install ruff && ruff check backend/; else echo "no backend/ yet — skipping"; fi`; likewise guard the frontend tsc step on `[ -f frontend/package.json ]`.
   - `config-validate`: validate only files that exist — guard each of
     `docker-compose.yml`, `docker-compose.dev.yml`, `frontend/package.json`,
     `frontend/tsconfig*.json` with a presence check; pass with a clear message if none
     exist yet.
   - `migration-check`: guard the whole alembic run on `[ -d backend/alembic ] || [ -f backend/alembic.ini ]`; skip-with-message otherwise. Use PartFolder env vars (`DATABASE_URL`, `DATA_DIR=/tmp/alembic-check`).
   - `compose-validate`: `if [ -f docker-compose.yml ]; then docker compose config --quiet; else echo "no compose yet — skipping"; fi`.
   - `image-build`: keep filament-bridge's "job always runs, build only on `pull_request`"
     shape, and additionally only attempt the build `if [ -f Dockerfile ]`.
   - `test`: guard on a test dir/files existing (`[ -d backend ] && backend has tests`);
     pass-with-message otherwise (standard exempts a repo with no tests yet).
   Add a short comment at the top of `ci.yml` noting the existence-guards are a
   **bootstrap tolerance** to be removed per-job as scaffolding adds each piece.

2. **`codeql.yml`** — copy filament-bridge's exactly (triggers, `security-extended`,
   matrix `[python, javascript-typescript]`, permissions). Keep its gating comment. No
   stack-specific changes needed; CodeQL no-ops gracefully on languages with no code.

3. **`publish.yml`** — copy filament-bridge's, change the image to
   `ghcr.io/crzykidd/partfolder3d`. Keep the dev/main/release tag matrix
   (`:dev`, `:sha-<short>`, `:latest`, `:<semver>`, `:<major>`). It only runs the build
   on push/release; until a `Dockerfile` exists the build step will fail, which is
   acceptable for `publish` (it's not a required PR check) — BUT add `if [ -f Dockerfile ]`
   guards / a checkout-then-guard so a push to `dev` without a Dockerfile does not error;
   prefer a leading job step that exits the job successfully when no `Dockerfile` is
   present (echo "no Dockerfile yet — nothing to publish").

4. **`retention.yml`** — copy filament-bridge's, change the package name to
   `partfolder3d` in both prune steps. Keep the keep-30-sha / keep-15-semver / protected-
   tags logic and the `workflow_run` + weekly schedule triggers.

## Conventions to honor

- Match filament-bridge's YAML style, action versions, and comment voice exactly except
  for the tailoring above.
- Do not invent jobs beyond the six in `ci.yml` + codeql + publish + retention.
- These are the `code-checkin-and-pr` required checks: lint, config, migration, compose,
  image-build, test, plus CodeQL (SAST). Don't add others.

## After authoring — docs

- **`standards.md`**: update the `code-checkin-and-pr` row Note to reflect that CI
  workflows are now committed (tolerant bootstrap), and that branch-protection
  required-status-checks wiring is handled by the orchestrator after the first run.
- **`docs/decisions.md`**: add a dated entry (newest at top) recording the tolerant-
  bootstrap decision and that required-status-checks are deferred to post-first-run.

## When done

1. Update this file's frontmatter: `status: completed` (or `failed`), `completed: 2026-06-27`,
   `result:` one line.
2. `git mv` this file into `prompts/done/` (create it if needed) on success, or
   `prompts/failed/` on failure.
3. Add a `docs/decisions.md` entry as above.
4. **You are a spawned agent: do NOT commit.** Prepare the working tree, then report back
   to the orchestrator: the list of files changed and a proposed one-line commit message
   (conventional prefix, e.g. `ci: add filament-bridge-style workflows (tolerant bootstrap)`),
   plus the exact CI job/check-run names you defined (so the orchestrator can wire branch
   protection). Do not push. Do not touch branch protection.
