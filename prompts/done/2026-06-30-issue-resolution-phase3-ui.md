---
name: 2026-06-30-issue-resolution-phase3-ui
status: done
created: 2026-06-30
model: sonnet            # frontend only
completed: 2026-06-30
result: >
  Replaced hardcoded ACTION_LABEL / ActionIcon / actionExtraStyle with a single
  ACTION_META map (10 action ids + unknown-fallback via toTitleCase). All new
  action ids covered with labels, lucide icons, danger flags, and confirm
  strings. handleAction now reads confirm from meta. tsc clean, vitest 229/229,
  vite build succeeded.
---

# Task: Issue resolution Phase 3b (frontend) — labels/icons for the new corrective actions

Phase 3a added corrective actions for all issue types. The Issues page already renders action
buttons generically from `issue.available_actions` and calls `POST /api/issues/{id}/action`, but
it only has label/icon/confirm metadata for the Phase-1 actions (`import`, `delete`, `ignore`).
Add metadata + confirmations for the new action ids. Frontend only.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md` (spawned agent on `dev`: do NOT commit/push
  — prepare the tree, report back). Do NOT edit `docs/decisions.md` — report notes back.
- Frontend stack: Tailwind + CSS-var Aurora theme + minimal Radix + lucide-react + TanStack
  Query + `apiFetch` CSRF wrapper. No Mantine, no toast (use `window.confirm`).
- Read fully:
  - `frontend/src/pages/admin/IssuesPage.tsx` — the page from Phase 2. It maps over
    `issue.available_actions` and renders a button per action id; `import` navigates to the
    wizard, others call `api.issueAction(id, action)` then refetch. Currently the label/icon/
    confirm handling is hardcoded for `import`/`delete`/`ignore`.
  - `frontend/src/lib/api/issues.ts` — `issueAction(id, action)` is already generic (any string
    action). No API change should be needed.

## Backend action ids (already implemented) → intended labels
Drive the UI from a single metadata map (action id → `{ label, icon, danger?, confirm? }`), so
new actions are trivial to add later. Handle ALL of these:

| action id | label | destructive? / confirm |
|---|---|---|
| `import` | Import… (opens wizard) | no (Phase 2 nav — keep as is) |
| `delete` | Delete folder | yes — confirm "Move this directory to trash?" (Phase 2 — keep) |
| `ignore` | Ignore | no (Phase 2 — keep) |
| `delete_item` | Delete item record | yes — confirm "Delete this item's database record? Its files are already gone." |
| `remove_record` | Remove file record | yes — confirm "Remove this missing file's record from the item?" |
| `accept` | Accept new hash | confirm "Accept the changed file and update its recorded hash?" |
| `clear_source` | Clear source URL | confirm "Clear this item's source URL?" |
| `keep_db` | Keep DB | confirm "Overwrite the sidecar with the database version?" |
| `keep_sidecar` | Keep sidecar | confirm "Update the database from the sidecar?" |
| `retry` | Retry rescan | no confirm |

Unknown/unlisted action ids: fall back to a sensible title-cased label + no confirm (don't crash).

## Working tree check
`git status --porcelain` first. Expect clean `dev` at `e3c2091` or later. If `IssuesPage.tsx` /
`issues.ts` have unrelated uncommitted changes, list them and ask.

## What to do
1. In `IssuesPage.tsx`, replace the hardcoded per-action handling with a **metadata map** keyed
   by action id: `{ label: string; icon: LucideIcon; danger?: boolean; confirm?: string }`.
   Pick sensible lucide icons (e.g. `FolderInput` import, `Trash2` delete/delete_item/
   remove_record, `EyeOff` ignore, `Check` accept, `Unlink`/`LinkOff` clear_source, `Database`
   keep_db, `FileText` keep_sidecar, `RefreshCw` retry). `danger` actions render in the red/
   danger colour; others neutral/ghost. `import` keeps green + the wizard navigation.
2. On click: if the action has a `confirm` string, `window.confirm(it)` first; then — for every
   action except `import` — call `api.issueAction(issue.id, action)` and refetch on success.
   `import` keeps its Phase-2 behavior (navigate to `/import/<import_session_id>?prefill=sidecar`).
3. Keep inline error surfacing (a 422/409 from the backend shows near the row, no crash). Keep
   the existing expand/detail, `target_path` display, and list layout intact.

## Verification (frontend — light)
- `npx tsc --noEmit`
- relevant `npx vitest run`
- `npx vite build` (the real gate)
Report all three.

## When done
1. Update frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`).
3. Do NOT edit `docs/decisions.md` — report any note back.
4. Do NOT commit/push. Report: files changed, note, one-line `feat:`-prefixed commit message,
   and tsc/vitest/vite-build results.
