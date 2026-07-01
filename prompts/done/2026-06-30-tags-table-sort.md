---
name: 2026-06-30-tags-table-sort
status: done
created: 2026-06-30
model: sonnet            # frontend only
completed: 2026-06-30
result: >
  DataTable extended with Column union type (string | SortableColumnDef); sortable
  headers render a button with ChevronUp/ChevronDown/ChevronsUpDown from lucide-react
  and a subtle opacity hover. TagAdminPage AllTagsSection gains sortKey/sortDir state,
  handleSort cycling function, and a useMemo-sorted tag array. Category and Uses
  headers wired as sortable; Tag name and Actions remain plain strings. All existing
  callers unchanged. tsc: clean, vitest: 229/229, vite build: success.
---

# Task: Sortable Category / Uses columns on the admin Tags table

On Content → All Tags (`/admin/content/tags`, `TagAdminPage`), let the operator click the
**Category** and **Uses** column headers to sort. Click cycles: unsorted → ascending →
descending → unsorted. Client-side only (the tag list is already fully loaded).

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md` (spawned agent on `dev`: do NOT commit/
  push — prepare the tree, report back). Frontend stack: Tailwind + CSS-var Aurora theme +
  lucide-react + TanStack Query; no Mantine/toast.
- Read fully:
  - `frontend/src/pages/admin/TagAdminPage.tsx` — the page. Table via `<DataTable
    columns={['Tag name', 'Category', 'Uses', 'Actions']}>` with `TagRow` children; each row
    shows `tag.category` and `tag.item_count` (the "Uses" value).
  - `frontend/src/components/ui/DataTable.tsx` — shared table. Today `columns: string[]`,
    rendered as plain `<th>` headers. **Used by other pages (e.g. JobsPage) — keep it
    backward compatible.**

## Working tree check
`git status --porcelain` first. Expect clean `dev` (a parallel agent is editing
`SettingsPage.tsx` / `api/settings.ts` / backend render files — NOT `DataTable`/`TagAdminPage`;
ignore its changes, don't stage/revert them). If `DataTable.tsx` or `TagAdminPage.tsx` have
unrelated uncommitted changes, list them and ask.

## What to do
1. **Enhance `DataTable` backward-compatibly** so a column may be either a plain `string`
   (unchanged) OR an object like `{ label: string; sortable?: boolean; sortDir?: 'asc' |
   'desc' | null; onSort?: () => void }`. For a sortable column, render the header as a
   clickable control with a direction indicator (lucide `ChevronUp`/`ChevronDown`, or a
   neutral/dimmed icon when `sortDir` is null). Plain-string columns render exactly as before.
   Keep types clean (`type Column = string | {...}`) and don't disturb existing callers.
2. **In `TagAdminPage`**, add sort state: `sortKey: 'category' | 'uses' | null` and
   `sortDir: 'asc' | 'desc' | null`. Clicking a sortable header cycles that column
   asc → desc → null (and switching columns starts at asc). Sort the tag array client-side
   before rendering rows:
   - `category`: string compare, case-insensitive; put null/empty categories last regardless
     of direction (they're "—").
   - `uses`: numeric compare on `item_count`.
   - When `sortKey` is null, preserve the current/default order.
   Pass the Category and Uses columns as sortable column objects wired to this state; leave
   "Tag name" and "Actions" as plain non-sortable headers.
3. Match existing styling; the header click target should have `cursor: pointer` and a subtle
   hover. Don't restyle the table otherwise.

## Verification (frontend — light)
- `npx tsc --noEmit`
- `npx vitest run` (fix any DataTable snapshot/type fallout)
- `npx vite build` (the real gate)
Report all three.

## When done
1. Update frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`).
3. Do NOT edit `docs/decisions.md` — report any note back.
4. Do NOT commit/push. Report: files changed, note, one-line `feat:` message, verify results.
