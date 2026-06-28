---
name: 2026-06-27-phase-10b-release-machinery
status: done
created: 2026-06-27
model: sonnet
completed: 2026-06-28
result: >
  CHANGELOG.md created (Phases 0–10 full feature set, Keep-a-Changelog format).
  release-prep.md and release-cut.md filled — all <PLACEHOLDER> tokens replaced,
  HTML-comment guide removed. README: version badge (teal 0FA4AB), stale badges
  updated, ## What's New section + v0.1.0 entry added, Roadmap updated to reflect
  shipped state. CI compose-validate fixed (standalone dev compose). CLAUDE.md and
  standards.md parked notes flipped to "filled". docs/decisions.md entry added.
  Both docker compose validations pass; no placeholder tokens remain.
---

# Task: Phase 10b — Make the release machinery functional (do NOT cut a release)

Fill the parked `/release-prep` + `/release-cut` command templates, create `CHANGELOG.md`,
wire the version source-of-truth, and fix one CI check. **This makes the release commands
runnable; it does NOT cut a release.** Part of **Phase 10** (build-plan).

## Hard guardrails
- **Do NOT cut a release, run `/release-prep` or `/release-cut`, bump the version number, push,
  open a PR, tag, or touch `main`.** Leave the version at the current `0.1.0`.
- **Do NOT touch application code, tests, UI pages, or `frontend/src/pages/examples/`.** This is
  docs / CI / command-template / changelog work only.

## Facts (use these exact values)
- **Version source-of-truth:** `backend/app/version.py` → `__version__ = "0.1.0"` (literal
  `__version__ = "<current>"`). `frontend/package.json` `"version": "0.1.0"` must be kept in
  sync — release-prep bumps BOTH.
- **Registry/image:** `ghcr.io/crzykidd/partfolder3d` (backend) + `ghcr.io/crzykidd/partfolder3d-frontend`.
- **Publish workflow:** `.github/workflows/publish.yml`, name **"Build and publish Docker
  images"**, triggers on push to `dev`/`main` and on `release: published`; tags `latest` on
  main/release and semver (`{{version}}`,`{{major}}`) on release. So `/release-cut` creating a
  GitHub release publishes `:latest` + `:<version>` + `:<major>`.
- **CI** (`.github/workflows/ci.yml`, name "CI"): jobs lint (ruff + tsc), config-validate,
  migration-check, compose-validate, image-build; plus `codeql.yml`. These are the green-gates.
- **Archive dir:** `docs/`.

## What to do

### 1. Create `CHANGELOG.md` (Keep-a-Changelog format)
- Standard header + an `## [Unreleased]` section (with a category skeleton comment) populated
  with the **user-facing feature set delivered so far** (Phases 0–10), grouped under Added /
  Changed / Fixed / Security. Draw from `docs/decisions.md` + the phase prompts in
  `prompts/done/`. Cover: identity/first-run/settings; libraries/storage/sidecar/atomic moves;
  catalog (search/FTS, tag cloud, browse, item page, downloads/ZIP); worker jobs + mesh
  rendering + job/scheduled-job monitors; import/inbox wizard (scraping, tag reconciliation,
  site-capabilities, instance import); reconcile engine (issues/change-log/reviews, auto/review);
  print history + sharing (tokenized public links, audit, instance export); AI tagging
  (Claude/OpenAI/Ollama, optional); admin (backup, JSON export, tag admin, API keys); and the
  Security entry for the SSRF guard + share-link private-data protections. Add an "Archived
  releases" index stub at the bottom.

### 2. Fill `.claude/commands/release-prep.md`
- Replace every `<PLACEHOLDER>` in the BODY (and remove/condense the top HTML-comment guide) with
  the real values: `<VERSION_FILE>`=`backend/app/version.py` (+ note frontend/package.json sync),
  `<VERSION_LITERAL>`=`__version__ = "<current>"`, `<README_BADGE_PATTERN>`=the version badge you
  add in step 4, `<README_WHATSNEW_SECTION>`=`## What's New`, `<DOCS_TO_SYNC>`=`CLAUDE.md` Status
  line (top of file) + this `prompts/startnewsession.md` is NOT a doc-sync target (skip it),
  `<LOCAL_CHECKS>`=the real CI commands (`ruff check backend/`; `cd frontend && npx tsc --noEmit`;
  `cd frontend && npx vitest run`; backend `pytest` (needs Postgres — note it); `alembic upgrade
  head` migration check; `docker compose config --quiet` AND `docker compose -f
  docker-compose.dev.yml config --quiet`), `<CHANGELOG_ARCHIVE_DIR>`=`docs/`.

### 3. Fill `.claude/commands/release-cut.md`
- Replace its placeholders with real values (image/registry, publish workflow name + that it must
  have pushed `:latest` before cutting, the CHANGELOG section as the GitHub release body, tag =
  `v<version>`). Keep the standard's safety rules (never re-tag; only after PR merged + main CI
  green + images published).

### 4. README version surface
- Add a **version badge** using brand teal — `![Version](https://img.shields.io/badge/version-0.1.0-0FA4AB)`
  — near the existing badges, and a **`## What's New`** section (place sensibly, e.g. above
  "Overview" or under it) with a `### v0.1.0 (<unreleased/today>)` placeholder entry. Set the
  release-prep `<README_BADGE_PATTERN>` to match the badge string (`version-<current>-0FA4AB`).
  Refresh the obviously-stale badges (`status-planning`, `stage-pre--alpha`, `code-none%20yet`)
  to reflect reality (e.g. `status-alpha`, `code-yes` / drop the "none yet").

### 5. Fix the CI compose check + flip the "parked" notes
- `.github/workflows/ci.yml` `compose-validate`: the "Validate dev compose overlay" step runs
  `docker compose -f docker-compose.yml -f docker-compose.dev.yml config` — but the dev compose
  is now **self-contained** (standalone, run with `-f docker-compose.dev.yml`). Change that step
  to validate it standalone: `docker compose -f docker-compose.dev.yml config --quiet` (rename
  the step to "Validate dev compose"). Keep the production-compose step.
- Update the now-stale "parked" notes: `CLAUDE.md` (the "Parked until scaffolding" block near the
  release section) and `standards.md` (the release-prep-and-cut row's "Parked:" note) → state the
  placeholders are now **filled** (version file `backend/app/version.py` + CI exist). Optionally
  update the CLAUDE.md top `Status:` line off "design/planning phase" to reflect that the app is
  built (alpha), but keep it light.

## Verify
- `docker compose config --quiet` and `docker compose -f docker-compose.dev.yml config --quiet`
  both pass. No code/tests touched (so pytest/tsc unaffected — don't run them). Grep that no
  literal `<PLACEHOLDER>`/`<VERSION_FILE>`-style tokens remain in the two command files.

## When done
1. Update this prompt's frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md` note (newest at top): version source-of-truth choice, release machinery
   filled, CI dev-compose-check fix.
3. **Do NOT commit/push/branch.** Report back: file list; proposed `chore(release):`/`docs:`
   commit message; confirmation no placeholders remain + both compose validations pass; and a
   one-line "ready to run `/release-prep <version>` when the owner wants to ship" note.
