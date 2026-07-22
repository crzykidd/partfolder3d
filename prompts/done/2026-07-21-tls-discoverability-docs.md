---
name: 2026-07-21-tls-discoverability-docs
status: done          # pending | in-progress | done | failed
created: 2026-07-21
model: sonnet            # coding task (small FE + docs)
completed: 2026-07-21
result: >
  Added an informational read-only "HTTPS / TLS" card to the admin Settings page
  (frontend/src/pages/settings/SettingsPage.tsx), expanded the README's existing
  "Built-in HTTPS" callout to name all three TLS_MODE values, added a one-clause
  TLS pointer to the "nginx config is baked" bullet, and added one CHANGELOG line.
  docs/tls.md was already correctly cross-linked from README and
  docs/features-overview.md (no fix needed). No settings-page test file exists in
  the repo, so per the prompt's fallback no test was added (noted for orchestrator).
  make verify-frontend: tsc + build always green; vitest showed the documented
  nondeterministic waitFor/timeout flake across three re-runs (different unrelated
  files each time — manyfold-admin, catalog-page, scrapers, setup-page — never
  settings-related); one clean run passed 27/27 files, 425/425 tests.
---

# Task: Make the nginx TLS/HTTPS setup discoverable (admin Settings pointer + README/docs)

The optional TLS/HTTPS feature landed (`TLS_MODE=off|selfsigned|provided`, see `docs/tls.md`),
but it's configured via `.env` + `docker-compose.yml` — a user looking for "SSL settings" won't
find it. Add a **discoverable pointer** in the admin Settings UI and flesh out the README's Docker
setup section so HTTPS is easy to find. This is a small frontend + docs change; **no backend, no
new stored settings** (TLS is deploy-level, not an app setting).

## Before you start

- **Read** `docs/tls.md` (the full TLS guide — the single source of truth to link to),
  `frontend/src/pages/settings/SettingsPage.tsx`, and the README "Production install" section
  (~lines 379-430). Skim `.env.example`'s TLS block (~lines 85-110) for the exact env names.
- **Working tree check:** `git status --porcelain` — the tree should be clean (the prior TLS
  commit is already on `dev`). Surface anything unexpected before editing.
- **No DB migration.** No new backend setting key. The Settings card is purely informational.

## What to do

### 1. Admin Settings page — informational HTTPS/TLS card

In `frontend/src/pages/settings/SettingsPage.tsx`, add a **read-only, admin-only** card in the
`{isAdmin && ( ... )}` block (a natural spot: a new section right after the existing "Instance
settings" card, or a subsection within it). It is NOT an editable `SettingRow` — TLS is set at the
container level, so there's nothing to PUT. The card should:
- Be titled something like **"HTTPS / TLS"** and match the Aurora styling of the existing cards
  (reuse the same `Card`, font sizes, `var(--aurora-*)` colors, `INLINE_CODE` style for env names).
- Explain in 2-4 lines that HTTPS is configured at the **deployment level** (in `.env` +
  `docker-compose.yml`), not in this UI, because nginx terminates TLS before the app is reached.
- Name the knobs: `TLS_MODE` (`off` default / `selfsigned` / `provided`), and the **`COOKIE_SECURE=true`**
  requirement when TLS is on.
- Point to the full guide: reference `docs/tls.md`. (A plain text/`<code>` reference to the path is
  fine; if you make it a link, link to the GitHub blob URL
  `https://github.com/crzykidd/partfolder3d/blob/main/docs/tls.md` and open in a new tab with
  `rel="noopener noreferrer"` — match how other external links in the app are rendered.)
- Keep it concise — this is a signpost, not a duplicate of `docs/tls.md`.

If a settings page test exists (check `frontend/src/test/` for something like `settings*.test.tsx`),
add/adjust a minimal assertion that the HTTPS card renders for an admin user. If none exists, do not
invent a whole new test harness — a light render assertion in an existing settings test is enough;
skip if there's no natural home and note that in your report.

### 2. README — Docker setup section

In `README.md` "Production install":
- Add a short **optional HTTPS step** (e.g. a "6. (Optional) Enable HTTPS" step after the first-run
  step, or a callout block right after the code fence) that summarizes the three `TLS_MODE` values in
  1-3 lines and points to `docs/tls.md`. Mirror the voice of the surrounding steps/callouts.
- Update the existing **"nginx config is baked…"** bullet (~line 424) to mention that the image also
  supports optional built-in TLS termination (`TLS_MODE`) — one clause, with the `docs/tls.md` pointer.
- Do NOT duplicate the whole `docs/tls.md` content into the README — link to it.

### 3. Docs coherence

- Confirm `docs/tls.md` is reachable from at least the README and `docs/features-overview.md` (the
  prior TLS commit should have added a features-overview section — verify it links/points correctly;
  fix if the cross-reference is missing or stale). Don't rewrite `docs/tls.md`.

### 4. Changelog

- `CHANGELOG.md [Unreleased]` already has the TLS `### Added` + base-bump `### Security` entries from
  the prior commit. Add ONE short line (under the existing `### Added`, or a new bullet) noting the
  in-app Settings pointer / improved HTTPS setup docs — keep it user-facing and brief. Do not
  duplicate the existing TLS entry.

## Verify

- **`make verify-frontend`** (`scripts/verify-frontend.sh` — fresh `tsc -b --force` → `npm run build`
  → `vitest run`) must pass. This is the gate for the Settings-page change.
  - Known flake: the local vitest gate can show nondeterministic `waitFor` 5s timeouts under CPU
    load (a *different* unrelated test each run) — if you see that, re-run once to confirm it's not
    your change, and note it; CI on a clean runner is authoritative. A *consistent* failure in a
    settings test IS your change — fix it.
- No backend changes, so `verify-backend` is not required.
- Sanity-read the rendered README section for correct Markdown.

## Conventions to honor

- Match existing SettingsPage styling exactly (inline styles + `var(--aurora-*)`, no new CSS system).
- Commit prefix `docs:` if it ends up docs-heavy, or `feat:` if the Settings card is the substantive
  part — **use `feat:`** (a new admin-visible UI element). No `Co-authored-by:` trailer. Changelog +
  docs in the SAME commit as the code.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decision in `docs/decisions.md` (only if there is one).
4. **You are a spawned agent: do NOT commit, do NOT push.** Prepare the tree, then report back to
   the orchestrator: the file list, a one-line commit message, and the `make verify-frontend`
   result (pass/fail + test count, plus a note if you hit the known flake).
