# Architecture & module map — PartFolder 3D

A navigation aid: find the right file fast without grepping. Two parts — a
**module map** (feature → where its code lives, including the test file) and the
**load-bearing gotchas** every change must respect.

Stack shape: FastAPI backend (`backend/app/`), arq worker (`backend/app/worker/`),
React/Vite frontend (`frontend/src/`), Postgres, Redis. Naming is near-1:1 across
router ↔ model ↔ api-client, so a feature's files usually share a stem.

---

## Documentation ecosystem — where things live

Which doc to read for what (so nobody looks for the roadmap in the PRD):

- **`CLAUDE.md`** — operating rules + verify discipline (durable how-we-work).
- **`docs/architecture.md`** — this file: module/where-things-live map + load-bearing gotchas.
- **`PRD.md`** — durable product intent & requirements (the *why*).
- **GitHub issues** (`gh issue list`) — near-term feature scope: what we're building **now**. The owner tracks active/planned work here, **not** in the PRD.
- **`docs/features-overview.md`** — as-built feature catalog (what exists today).
- **`CHANGELOG.md`** — release history.
- **`docs/decisions.md`** — ADR log, newest-first.
- **`prompts/startnewsession.md`** — the lean live-state handoff for a fresh session.

---

## Module map

One row per subsystem. Paths are relative to repo root. Backend routers live in
`backend/app/routers/`, models in `backend/app/models/`, worker tasks in
`backend/app/worker/` (+ `worker/tasks/`), storage/services in
`backend/app/storage/` and `backend/app/services/`; frontend api clients in
`frontend/src/lib/api/`, pages in `frontend/src/pages/`; backend tests in
`backend/tests/`, frontend tests in `frontend/src/test/`.

| Feature | Router | Model(s) | Worker task | Storage/service | API client | Page(s) | Test file(s) |
|---|---|---|---|---|---|---|---|
| Items / catalog | `items.py` | `item.py`, `file.py`, `image.py`, `favorite.py` | `tasks/render.py`, `tasks/analysis.py` | `storage/paths.py`, `storage/inventory.py`, `services/item_helpers.py` | `items.ts` | `CatalogPage.tsx`, `ItemPage.tsx`, `pages/item/*` | `test_phase2_items.py`, `test_phase3_catalog.py`, `test_item_files.py`, `test_phase14_item_images.py`, `test_phase15_local_modified.py`; FE `catalog.test.ts`, `carousel.test.ts` |
| Import sessions / bulk import | `import_sessions/` (`sessions.py`, `helpers.py`, `__init__.py`) | `import_session.py` | `tasks/import_session.py` | `storage/scraper.py`, `storage/archive.py` | `import.ts` | `ImportsPage.tsx`, `ImportWizardPage.tsx`, `pages/import-wizard/*` | `test_phase5_import.py`, `test_bulk_import.py`, `test_import_management.py`, `test_url_wizard_attach.py`; FE `import-wizard.test.ts`, `bulk-import.test.ts`, `import-wizard-steps.test.tsx` |
| Shares (item + site) / public share | `shares.py`, `site_capabilities.py` | `share_link.py`, `share_audit_event.py`, `site_capability.py` | — | `storage/paths.py` (traversal guards) | `shares.ts` | `PublicSharePage.tsx`, `pages/item/ShareControls.tsx`, `admin/ShareAuditPage.tsx`, `admin/SiteCapabilitiesPage.tsx` | **Share assertions span several files:** `test_phase7_sharing.py` (primary), plus expiry/revocation/privacy checks in `test_phase7_print_history.py`, `test_phase9_admin.py`, `test_phase15_local_modified.py` |
| Issues / reconcile | `issues.py`, `changes.py` | `issue.py`, `change_log.py` | `worker/reconcile.py`, `tasks/scheduled.py` | `storage/sidecar.py`, `storage/inventory.py` | `issues.ts`, `changes.ts` | `admin/IssuesPage.tsx`, `admin/ChangesPage.tsx` | `test_phase6_reconcile.py`, `test_issue_resolution.py`; FE `reconcile-ui.test.ts` |
| Jobs / job lifecycle | `jobs.py` | `job.py` | `worker/job_tracker.py` (create/transition) | — | `jobs.ts` | `admin/JobsPage.tsx` | `test_phase4_jobs.py`, `test_job_lifecycle.py`, `test_item_jobs_endpoint.py` |
| Print history | `print_records.py` | `print_record.py` | — | — | `print-records.ts` | `pages/item/PrintHistory.tsx`, `admin/PrintStatsPage.tsx` | `test_phase7_print_history.py`; FE `print-history.test.ts` |
| AI tagging / AI usage | `ai_actions.py`, `ai_providers.py`, `ai_usage.py` | `ai_provider.py`, `ai_usage.py` | — (called inline) | — | `ai.ts` | `admin/AiProvidersPage.tsx`, `admin/AiUsagePage.tsx` | `test_phase8_ai.py`, `test_phase13_ai_usage.py`, `test_starter_tags_ai_status.py`; FE `ai-providers.test.ts` |
| Scrapers / fallback backends | `agentql.py` | `scraper_usage.py`, `site_capability.py` | `tasks/import_session.py` | `storage/scraper.py` (`extract_metadata_from_html`), `storage/agentql_client.py`, `storage/flaresolverr_client.py`, `storage/ssrf_guard.py` | `agentql.ts`, `scrapers.ts` | `admin/SiteCapabilitiesPage.tsx` (AgentQL + FlareSolverr cards) | `test_agentql.py`, `test_flaresolverr.py` |
| Libraries | `libraries.py` | `library.py` | — | `storage/paths.py`, `storage/journal.py` | `libraries.ts` | `admin/LibrariesPage.tsx` | `test_libraries.py` |
| Backups | `backup.py` | `backup.py` | `tasks/backup.py`, `worker/backup.py` | — | `backups.ts` | `admin/BackupsPage.tsx` | (covered in `test_phase9_admin.py`) |
| Tags / tag-admin | `tags.py`, `tag_admin.py` | `tag.py` | — | — | `tag-admin.ts` (+ tag ops in `items.ts`) | `admin/TagAdminPage.tsx`, `admin/PendingTagsPage.tsx` | `test_tag_delete_and_browse_counts.py`, `test_tag_search_autocomplete.py`, `test_starter_tags_ai_status.py` |
| Creators | `creators.py` | `creator.py` | — | — | (via `items.ts`) | `CreatorPage.tsx`, `MyCreationsPage.tsx` | (covered in item/import tests) |
| Mesh / 3MF analysis & 3D viewer | `items.py` (preview_3d), `downloads.py` | `file.py`, `image.py` | `worker/mesh_analysis.py`, `worker/threemf.py`, `worker/render_mesh.py`, `worker/render_subprocess.py`, `tasks/render.py`, `tasks/analysis.py` | `storage/gcode_parser.py` | `items.ts` | `pages/item/ObjectBreakdown.tsx`, `ThreeMfPanel.tsx`, 3D viewer | `test_object_analysis.py`, `test_threemf.py`, `test_threemf_thumbnail_path.py`, `test_render_reliability.py`; FE `viewer.test.tsx`, `threemf-panel.test.tsx`, `object-breakdown.test.tsx` |
| Downloads / export | `downloads.py`, `export.py` | `download_bundle.py` | `tasks/bundles.py` | `storage/archive.py` | `export.ts` | `admin/ExportPage.tsx` | (covered in `test_phase9_admin.py`, archive in `test_archive.py`) |
| Scheduled jobs | `scheduled_jobs.py` | `scheduled_job.py` | `tasks/scheduled.py` | — | `scheduled-jobs.ts` | `admin/ScheduledJobsPage.tsx` | (covered in `test_phase9_admin.py`) |
| Reviews | `reviews.py` | `review_item.py` | `tasks/reviews.py` | — | `reviews.ts` | `admin/ReviewsPage.tsx` | (covered in `test_phase9_admin.py`) |
| Storage / atomic moves / sidecar | (used across items/libraries/reconcile) | — | `worker/reconcile.py` | `storage/journal.py`, `storage/paths.py`, `storage/keys.py`, `storage/inventory.py`, `storage/sidecar.py` | — | — | `test_phase2_storage.py` |
| Settings / dashboard / nav | `settings.py`, `me.py` | `setting.py`, `user.py` (per-user layout) | — | — | `settings.ts`, `me.ts` | `settings/SettingsPage.tsx`, `settings/QuickStartPage.tsx`, nav shells | `test_settings.py`, `test_phase11_nav_layout.py`, `test_phase12_dashboard.py`; FE `dashboard.test.ts`, `navConfig.test.ts` |
| Auth / setup / api-keys / invites / password-reset | `auth.py`, `setup.py`, `api_keys.py`, `invites.py`, `password_reset.py`, `users.py` | `user.py`, `session.py`, `api_key.py`, `invite.py`, `password_reset.py` | — | `app/crypto.py`, `app/auth/` | `auth.ts`, `setup.ts`, `api-keys.ts`, `invites.ts`, `password-reset.ts`, `users.ts` | `LoginPage.tsx`, `SetupPage.tsx`, `InviteAcceptPage.tsx`, `ResetPasswordPage.tsx`, `settings/ApiKeysPage.tsx`, `admin/UsersPage.tsx`, `admin/InvitesPage.tsx`, `admin/PasswordResetPage.tsx` | `test_auth.py`, `test_setup.py`, `test_api_keys.py`, `test_invites.py`, `test_password_reset.py`, `test_users.py`, `test_phase10a_hardening.py`, `test_crypto.py`; FE `auth.test.tsx`, `setup-page.test.tsx` |

> **Test-map note:** backend test files are still phase-named, so "which tests
> cover shares?" isn't one file — share assertions are spread across the rows
> flagged above. New test files should be feature-named. The FE tests are
> feature-named already.

---

## Load-bearing gotchas / constraints

Durable technical traps. Break one and the failure is often silent or
image-only (invisible to local unit runs).

- **Render backend uses the `vtk-osmesa` wheel + `libosmesa6`** (NOT stock PyPI
  `vtk`, which is X11-only). Only verifiable in a **built image**, not a bare
  local run.
- **3MF is read, not server-rendered.** It uses the embedded slicer thumbnail +
  in-browser capture; server render covers only `.stl/.obj/.ply`
  (`worker/render_mesh.py MESH_EXTENSIONS`). An **all-3MF item skips server
  render** entirely. (Mesh *analysis* does include `.3mf` —
  `mesh_analysis.py MESH_ANALYSIS_EXTENSIONS = {.stl,.3mf,.obj,.ply}`.)
- **Fixed modals must portal to `<body>`.** Aurora cards use `backdrop-filter`,
  which traps a `position:fixed` child inline (bit the 3D viewer + description
  modal). Portal fixed overlays out to `<body>`.
- **The dev worker has NO hot-reload.** `uvicorn --reload` hot-reloads the
  backend; the worker runs plain `python worker.py`. **Restart it after any
  worker/task/scraper edit** (`make worker-restart`, or
  `docker compose -f docker-compose.dev.yml restart worker`).
- **To recover a wedged stack, bring it up WITHOUT the worker first:**
  `docker compose -f docker-compose.dev.yml up -d db redis backend frontend nginx`,
  then start the worker (with its cpu/mem caps). Worker resource limits
  (`WORKER_MAX_JOBS` / `RENDER_CONCURRENCY` / `ANALYZE_CONCURRENCY` +
  compose `WORKER_CPUS` / `WORKER_MEM_LIMIT`) default small so a bulk import
  can't overrun the host.
- **Release CI shape — don't break it.** `main`'s required checks bind by
  **BARE job name** — `Lint`, `Test`, `Migration check`, `Compose validation`,
  `Config validation`, `Image build` — which are the `ci.yml`
  `pull_request:[main]` jobs. **Don't rename those jobs.** `dev-checks.yml` =
  fast, non-required `(dev)`-suffixed checks on `push:[dev]` (lint runs here too
  — it caught a real F811 dupe). `publish.yml` = 3-image matrix
  (`partfolder3d`, `-frontend`, `-nginx`) on push:main + release. **CodeQL is
  NOT a required check** (doesn't block merge) but flags real issues on release
  PRs — **fix the real ones, dismiss false positives** via the code-scanning API
  (`gh api .../alerts/N -f state=dismissed`, comment ≤ 280 chars).
- **Merging two branches that touch the same feature:** a clean text-merge is
  NOT enough — both may add the same symbol/route (bit us: duplicate
  `/{key}/jobs` endpoint + `ItemJobOut`/`ItemJobSummary`). After merging,
  **grep for duplicate symbols/routes and run a FRESH full build** — worktree
  agents' `tsc -b` incremental cache HID the error (see verify-frontend's
  `--force`).
- **Migration numbering is serialized.** Tasks creating an Alembic migration run
  one-at-a-time; the orchestrator assigns the next `00NN` in the handoff prompt.
  Parallel agents both creating `0023_*` collide. (Head is `0022` as of v0.3.0.)
