---
name: 2026-07-17-manyfold-3-frontend
status: done          # pending | in-progress | done | failed
created: 2026-07-17
model: sonnet
completed: 2026-07-17
result: >
  Admin Manyfold instances page (ManyfoldPage.tsx at /admin/ai/manyfold, 4th AI-tab)
  with add/edit/rotate-secret/test-connection/delete; new manyfold.ts API client;
  import wizard gained a conditional Assets step (shown when session.files.length > 0)
  for reviewing/deselecting staged files, wired via a hasFiles-aware nextStep/prevStep/
  StepProgress; SummaryStep's Files row reflects the selected count. make verify-frontend
  green: 425 tests / 27 files.
---

# Task: Manyfold connector — Part 3: admin UI + wizard asset selection

Wire up the frontend for the Manyfold connector: an admin screen to register/enable
Manyfold instances (Part 1 backend) and paste OAuth credentials, and the import-wizard
affordance to review the pulled 3D files (Part 2 backend). This is **Part 3 of 3**; the
backend (Parts 1 & 2) is already merged. Stay in scope.

## Context you need (read first)

- **Backend contracts (already merged):**
  - Admin: `/api/admin/manyfold` — `GET /` list, `POST /` create
    (`base_url, display_name, client_id, client_secret, scopes`), `GET /{id}`,
    `PATCH /{id}` (update fields / rotate `client_secret` / toggle `enabled`),
    `DELETE /{id}`, `POST /{id}/test-connection` → `{ok, scope}` or structured error.
    Responses expose `has_secret` + `client_id`, **never** the secret. Read the actual
    router/schemas in `backend/app/routers/manyfold.py` for exact field names before
    coding the client.
  - Import session detail now includes staged `files` (`id, original_name, role, size,
    selected`) and a `PATCH /api/import-sessions/{id}/files/{file_id}` `{selected}` toggle
    (confirm the exact route/shape in `backend/app/routers/import_sessions/`).
- **Frontend stack (match it — do NOT introduce new libs):** Tailwind + CSS-var theme,
  minimal Radix, lucide icons, TanStack Query, `apiFetch` (CSRF). No Mantine, no toast
  library.
- **Reference components / clients:**
  - `frontend/src/lib/api/import.ts`, `frontend/src/lib/api/scrapers.ts`,
    `frontend/src/lib/api/agentql.ts` — API-client patterns (typed fns over `apiFetch`).
    You add `frontend/src/lib/api/manyfold.ts`.
  - `frontend/src/pages/admin/SiteCapabilitiesPage.tsx` — the admin provider UI (the
    "Scrapers" section with per-provider cards, `SetTokenPanel` for a write-only secret,
    test-connection buttons, `UsagePanel`). This is the model for the Manyfold admin UI,
    and likely where it lives (or an adjacent admin page — match the existing admin nav).
  - `frontend/src/pages/ImportWizardPage.tsx` + `frontend/src/pages/import-wizard/*`
    (`TitleStep`, `ImagesStep`, `TagsStep`, `CreatorStep`, `SummaryStep`, `StepProgress`).
    You add an **Assets/Files step**.
  - `frontend/src/components/AddAssetModal.tsx` — the "From URL" entry point (no change
    needed for detection — the backend recognizes the domain; an optional hint is fine).
- **Tests:** `frontend/src/test/scrapers.test.tsx`,
  `frontend/src/test/import-wizard-steps.test.tsx`,
  `frontend/src/test/import-wizard-page.test.tsx` — the patterns to mirror.
- **Verify discipline:** `CLAUDE.md`. Frontend gate is `make verify-frontend`
  (**fresh** `tsc -b --force` → `npm run build` → `vitest run`). The `--force` matters:
  `tsc -b`'s incremental cache HIDES real type errors.

## Working tree check

Run `git status --porcelain`. Only this prompt should be dirty. If a file you plan to edit
has uncommitted changes, list it and stop.

## What to do

1. **API client** — `frontend/src/lib/api/manyfold.ts`: typed functions for list / create /
   get / update / delete / test-connection over `apiFetch`, plus the TS types mirroring the
   backend schemas (secret write-only; `has_secret` on responses). Match `scrapers.ts`.
2. **Admin UI** — a **Manyfold instances** screen/section (list-based, since multiple
   instances are supported):
   - A list of configured instances: display name / base_url / domain, enabled toggle,
     `has_secret` indicator, `last_connected_at`, a **Test connection** button (surfaces
     `{ok, scope}` or the error inline), and delete.
   - An **Add instance** form: base_url, display name, client ID, client secret, scopes
     (default `public read`). On existing rows, a secret field that is blank unless you're
     replacing it (write-only rotate) — mirror `SetTokenPanel`.
   - Place it consistently with the existing admin surface (a section on
     `SiteCapabilitiesPage.tsx` next to Scrapers, or a sibling admin page reached from the
     same admin nav — pick what matches the current nav structure and note the choice).
   - Include a short helper line telling the admin where to create the credentials on their
     instance: `{base_url}/oauth/applications`, grant type client-credentials, scopes
     `public read`.
3. **Wizard Assets step** — a new step in `frontend/src/pages/import-wizard/` that lists
   the session's staged `files` (`original_name`, `role`, human-readable `size`) each with
   a checkbox bound to `selected`, **checked by default** (the backend defaults
   `selected=true`). Toggling calls the PATCH endpoint. Wire it into `ImportWizardPage`'s
   step sequence and `StepProgress` — show it when the session has staged files (so it also
   benefits plain uploads); place it before Summary. The Summary step should reflect the
   count of selected files.
   - The existing Images / Tags / Creator steps already read session data — verify they
     render the Manyfold-pulled images, the full tag list in the picker, and the creator
     without change; fix only if something doesn't display.
4. **Tests** — Vitest:
   - `frontend/src/test/manyfold-admin.test.tsx` (mirror `scrapers.test.tsx`): render the
     admin UI against a mocked API — list, add, test-connection success + failure, secret
     is never rendered back, enable toggle, delete.
   - Extend the import-wizard step tests: the Assets step lists files, boxes checked by
     default, unchecking fires the PATCH, Summary reflects the selected count.
   - Keep `vitest run` green.

## Conventions to honor

- Match existing component structure, Tailwind usage, theme CSS-vars, and the `apiFetch`
  CSRF pattern. No new dependencies.
- **CHANGELOG.md `[Unreleased]`** entry in THIS commit (Added: "Admin UI to configure
  Manyfold instances; import wizard lets you review/deselect pulled 3D files").
- **docs/architecture.md**: add the frontend rows (manyfold api client, admin screen,
  wizard Assets step).
- **docs/decisions.md** (newest first): note where the admin UI lives and the Assets-step
  visibility rule if non-obvious.
- Secret is never rendered back from the server; the input is write-only.

## When done

1. Run **`make verify-frontend`** to green (fresh `tsc -b --force` → `npm run build` →
   `vitest run`). Do not rely on the incremental cache.
2. Update this file's frontmatter + `git mv` into `prompts/done/` (or `prompts/failed/`).
3. **Spawned agent: do NOT commit or push.** Report back: files changed, a proposed
   `feat:` one-liner, the verify result, and any decisions/deviations.
