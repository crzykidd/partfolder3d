---
name: 2026-07-01-docs-refresh-pre-release
status: done
created: 2026-07-01
model: sonnet            # docs
completed: 2026-07-01
result: >
  Updated README.md (What's New summary, Rendering, Reconciliation, Tagging, Admin
  sections) and docs/features-overview.md (expanded Failed-job retry → Job monitor /
  lifecycle; new Render reliability and controls section; new Issue resolution
  per-type actions section; Tag improvements + Aurora UI sections extended).
  docs/nav-architecture.md required no changes — new features are enhancements to
  existing listed pages, no new routes or sections added.
---

# Task: Refresh README + Getting Started + features docs for the pre-release state

Since the last docs refresh, a large batch of features shipped. Update the user-facing docs so
they accurately describe the current product before the v0.1.0 release. Verify every claim
against the actual code/routes — do NOT document anything that isn't really there.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md` (spawned agent on `dev`: do NOT commit/push
  — prepare the tree, report back). Do NOT edit `docs/decisions.md`.
- Read the docs you'll touch: `README.md` (features + Getting Started sections),
  `docs/features-overview.md` (per-feature reference with admin routes), and
  `docs/nav-architecture.md` (admin nav / routes) — plus `.env.example` for the env vars.

## What to add / update (verify each against the code before writing)
Fold these newly-shipped capabilities into the appropriate docs (features list, feature-overview
entries, and any admin-route/nav references). Keep the existing structure; extend, don't rewrite.

1. **Render reliability + controls.** Mesh renders now run in an isolated subprocess with a
   wall-clock timeout and CPU-thread caps, and orphaned "running" renders are recovered on worker
   restart. New knobs: env `RENDER_TIMEOUT_S` (default 300), `RENDER_CPU_THREADS` (default 2), and
   a **`RENDER_MODE` admin setting** (Settings → Instance settings): *Render all models* /
   *Render only when a model has no images* / *Disable rendering* (also env `RENDER_MODE`, DB
   overrides env). Verify in `backend/app/config.py`, `backend/app/worker/tasks/render.py`,
   `frontend/src/pages/settings/SettingsPage.tsx`.
2. **Job monitor / lifecycle.** The admin job monitor (`/admin/activity/jobs`) now supports:
   cancel + restart of running jobs; retry that supersedes the old failed job once it succeeds;
   a context-sensitive "Clear …" button (by active status filter); an archive view; and a daily
   **retention** prune (succeeded 7 days / failed 30 days, both configurable via
   `JOB_RETENTION_SUCCEEDED_DAYS` / `JOB_RETENTION_FAILED_DAYS`). Verify in
   `backend/app/routers/jobs.py`, `frontend/src/pages/admin/JobsPage.tsx`.
3. **Issue resolution.** The admin Issues page (`/admin/activity/issues`) now offers actionable,
   per-type resolution instead of a no-op "mark resolved": orphaned directory → Import (opens the
   wizard prefilled from the folder's sidecar) / Delete (→ trash) / Ignore; plus per-type actions
   for conflict (keep DB / keep sidecar), dead_link (clear source URL), corruption (accept new
   hash), missing_file (remove record), sidecar_error (retry). Resolving/ignoring now **sticks**
   (the scan dedupes and no longer re-creates the same issue). Verify in
   `backend/app/routers/issues.py`, `backend/app/worker/reconcile.py`,
   `frontend/src/pages/admin/IssuesPage.tsx`.
4. **Catalog / tags polish.** Global stat tiles are clickable (navigate to their detail pages);
   the admin Tags table (`/admin/content/tags`) is sortable by Category / Uses; dark-mode native
   dropdowns render dark. (Keep these brief — they're small.)
5. **`.env.example` cross-check.** Ensure the docs' env references match `.env.example`
   (RENDER_* , JOB_RETENTION_* are all present there already — just keep docs consistent).

## Conventions to honor
- Match the existing doc voice/format. Keep the version at `0.1.0` (bare, no `v`). Do not bump
  the version or touch `backend/app/version.py` / `frontend/package.json` — the release command
  handles that.
- Accuracy over completeness: if you can't confirm a feature in the code, leave it out and note it.

## Verification
- No build step for docs. Cross-check every added claim against the cited source files.
- Run a markdown link sanity check if easy (no broken relative links you introduced).

## When done
1. Update frontmatter (`status`, `completed: 2026-07-01`, `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`).
3. Do NOT edit `docs/decisions.md` — report any note back.
4. Do NOT commit/push. Report: files changed, a short list of what you added per doc, any claim
   you left out for lack of confirmation, and a one-line `docs:`-prefixed commit message.
