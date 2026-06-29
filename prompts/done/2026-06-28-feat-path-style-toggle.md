---
name: 2026-06-28-feat-path-style-toggle
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  Added toPathStyle(path, 'windows'|'posix') helper to catalog-utils.ts with 7 unit tests.
  Updated PathPrefixSection in SettingsPage.tsx with path style toggle (FilterPill pair),
  live preview using rewritePath(SAMPLE_DIR_PATH, draft), and clearer copy.
  tsc clean, vitest 198/198, vite build success. No backend changes.
---

# Task: Per-user path display — explicit Windows/Linux style toggle + discoverable Settings UX

The per-user **path prefix** (Settings → "Per-user path prefix", `PUT /api/me/path-prefix`) already
rewrites the on-disk path shown on item pages to where the user accesses the files. And
`rewritePath` (`frontend/src/lib/catalog-utils.ts`) already infers Windows vs POSIX separators from
whether the prefix contains `\`. The gap is **discoverability + explicitness**: users don't know
where to set it or that the separator follows the prefix style. Add an explicit
**Windows (`\`) / Linux·macOS (`/`)** choice + a live preview, and clearer copy. **Frontend only —
no backend, no migration** (leverage the existing inference; the saved prefix string encodes the
style via its separators).

## What to do (all in the path-prefix section of `frontend/src/pages/settings/SettingsPage.tsx`)
- Add a clear **Path style** control: **Windows (`\`)** vs **Linux / macOS (`/`)** (toggle/radio,
  Aurora-styled). Selecting a style **normalizes the separators in the prefix input** to that style
  (convert `/`↔`\` in the current prefix text) so the saved prefix encodes the chosen style — which
  `rewritePath` already keys off. Default the toggle from the current prefix (contains `\` →
  Windows, else Linux/macOS).
- Add a **live preview**: take a representative item dir path (e.g. a sample like
  `/library/main/Creator/Cool-Thing` — or, if easy, the real shape) and show
  `rewritePath(sample, prefix)` updating as the user edits the prefix / flips the style, so they see
  exactly how their paths will render.
- Improve the section copy so it's self-explanatory: what the prefix does (maps the stored path to
  where *you* open the files), an example per OS (`Z:\3dprints` / `/mnt/nas/3dprints`), and that the
  style controls `\` vs `/`.
- Factor the separator-normalization into a small helper in `catalog-utils.ts` (e.g.
  `toPathStyle(path, 'windows' | 'posix')`) and unit-test it; keep `rewritePath`'s existing
  inference behavior intact (don't break current saved prefixes).
- Keep the existing save flow (`PUT /api/me/path-prefix`) and all other Settings features intact.

## Constraints
- **Frontend only.** No backend, no model, no migration, no api.ts endpoint changes (the existing
  `path-prefix` get/set stays as-is). Tailwind + Aurora + `@/components/ui` + lucide. NO new deps.
  Don't touch `frontend/src/pages/examples/`.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (add a unit test for
  `toPathStyle` / the preview logic); **and `npx vite build` MUST succeed** (the real gate). Do NOT
  commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: one line — explicit style toggle normalizes the prefix separators;
   `rewritePath` inference unchanged; no backend needed.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; tsc / vitest / **vite build** results; confirmation no backend change + existing
   prefixes still work; anything unverified.
