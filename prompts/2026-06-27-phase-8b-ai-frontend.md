---
name: 2026-06-27-phase-8b-ai-frontend
status: pending          # pending | completed | failed
created: 2026-06-27
model: sonnet            # React/TS UI wiring against a locked backend
completed:
result:
---

# Task: Phase 8b — AI tagging frontend

Add the **Phase 8 frontend** for the optional AI assist features. The backend
(Phase 8a) is complete. This handoff covers **only the frontend** — three
UI surfaces that call the Phase 8a endpoints.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) Phase 8 + Locked build-time decisions.
- Read [`PRD.md`](../PRD.md) §13 (admin AI-provider settings) + §5.3 (AI tag flow).
- Read [`CLAUDE.md`](../CLAUDE.md) operating rules.
- Read [`docs/decisions.md`](../docs/decisions.md) — Phase 8a section, then the
  Phase 1b/3b/5b/7b frontend-decisions sections for coding conventions (no Mantine,
  no toast library, CSS-variable theme, how inline feedback works, etc.).

## UI stack — MANDATORY, no deviations

The project does **not** have Mantine or any toast library. Work only with:

- **Tailwind CSS v4** (`@tailwindcss/vite` plugin, CSS-variable theme in `src/index.css`,
  class-based dark mode, no `tailwind.config.ts`)
- **Shadcn/ui CSS-variable theme only** — Tailwind utility classes + `bg-background`,
  `text-foreground`, `text-muted-foreground`, `text-primary`, `border`, `border-input`,
  `bg-card`, `bg-muted`, `ring-ring`, `input-base` component class, etc.
- **Minimal Radix UI**: only `@radix-ui/react-dropdown-menu` and `@radix-ui/react-slot`
  are in `package.json`. Do NOT add `@radix-ui/react-dialog`, tabs, select, etc.
  Custom overlays use a `div` with `fixed inset-0 z-50 bg-black/60` backdrop (see
  `AddAssetModal.tsx` for the pattern).
- **lucide-react** for icons.
- **TanStack Query** (`@tanstack/react-query`) for all server state — `useQuery` /
  `useMutation`. No manual `fetch` calls outside `src/lib/api.ts`.
- **`apiFetch` / `apiFetchForm`** CSRF wrappers from `src/lib/api.ts` — every mutating
  call goes through these. Read `api.ts` before writing any API call.
- Inline transient feedback (inline "✓ Saved" / "Error: ..." text for 3 s) rather than
  a toast. See `ShareSection` in `ItemPage.tsx` for the copy-on-mint pattern.
- `@tanstack/react-table` is available for tables; `@tanstack/react-virtual` for
  virtualized lists. Vitest for unit-testable pure logic.
- React Router `useNavigate` / `NavLink` for routing.

## Working tree check

Run `git status --porcelain` before touching files. No Phase 8a files should be
dirty (they were committed). Surface any unexpected dirty files and ask before
touching them.

## Phase 8a backend endpoints to call

All require session cookie + CSRF header via `apiFetch`.

### AI-provider CRUD — `/api/ai-providers` (admin-only)

| Method | Path | Body / Notes |
|--------|------|-------------|
| `GET` | `/api/ai-providers` | List all providers. Response: `AiProviderOut[]` |
| `POST` | `/api/ai-providers` | Create. Body: `{provider, endpoint?, model?, api_key?, enabled}` |
| `GET` | `/api/ai-providers/{id}` | Get one |
| `PATCH` | `/api/ai-providers/{id}` | Update. Body: `{endpoint?, model?, api_key?, enabled?}` |
| `DELETE` | `/api/ai-providers/{id}` | Delete. Returns 204 |
| `POST` | `/api/ai-providers/{id}/enable` | Toggle. Body: `{enabled: bool}` |
| `POST` | `/api/ai-providers/test` | Test connection without saving. Body: `{provider, endpoint?, model?, api_key?}` |

**`AiProviderOut` shape:**
```ts
{
  id: number
  provider: 'claude' | 'openai' | 'ollama'
  endpoint: string | null
  model: string | null
  has_key: boolean   // true when a key is set — key itself is NEVER returned
  enabled: boolean
}
```

`api_key` is **write-only** — never display it; `has_key` tells the UI whether one is set.

### AI actions — import-session context (authenticated)

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/api/import-sessions/{id}/ai/suggest-tags` | Returns `AiTagSuggestionOut` |
| `POST` | `/api/import-sessions/{id}/ai/cleanup-description` | Returns `AiTextOut` |
| `POST` | `/api/import-sessions/{id}/ai/summarize` | Returns `AiTextOut` |

**`AiTagSuggestionOut`:**
```ts
{
  canonical: string[]       // existing active tags that match
  new_suggestions: string[] // new tags to surface in pending queue (≤ 5)
  provider_available: boolean
  error: string | null
}
```

**`AiTextOut`:**
```ts
{
  text: string | null
  provider_available: boolean
  error: string | null
}
```

Contract: when `provider_available === false`, the UI shows nothing (no error).
When `error !== null`, show inline error text. When `text` is returned, offer it
as a suggestion the user must explicitly accept — **never auto-apply**.

## What to build

### Surface 1 — AI Provider Settings page (admin)

**Route:** `/admin/ai-providers` (add to `App.tsx` inside `AdminGuard`)

**File:** `frontend/src/pages/admin/AiProvidersPage.tsx`

Add a **"AI Providers"** nav link in `AppShell.tsx` admin nav section (visible
only when `user.role === 'admin'`).

UI requirements:
- List all configured providers (from `GET /api/ai-providers`) with their type,
  model, endpoint, has_key badge, and enabled toggle.
- **Add provider** inline form (or inline expand-row, not a dialog — no Radix Dialog).
  Fields: provider type (3 radio buttons or simple button group: Claude / OpenAI /
  Ollama), endpoint (visible only for Ollama), model (text input, placeholder shows
  default: `claude-opus-4-8` for Claude, `gpt-4o-mini` for OpenAI, required for
  Ollama), API key (text input, password type, placeholder "Enter key — write-only;
  stored encrypted"). Submit creates the provider.
- **Edit row**: inline key-rotation (password input + rotate button), model + endpoint
  edit, enabled toggle via `PATCH`, delete button.
- **Test connection** button calls `POST /api/ai-providers/test` with the current
  unsaved inputs. Shows "✓ Connection OK" or "Error: <msg>" inline for 3 s.
- When `has_key` is `true`, show a `••••••••` placeholder (not the real key).
  Never show the key; only allow replacing it.
- The UI must work gracefully with zero providers (shows "No AI providers configured"
  + Add button).

### Surface 2 — AI actions in ImportWizardPage

**File:** `frontend/src/pages/ImportWizardPage.tsx` (edit existing)

The wizard has tag and description steps. Add opt-in AI action buttons where they
fit:

**Tag step (where the user adds tags):**
- A small "Suggest tags (AI)" button. On click: calls
  `POST /api/import-sessions/{id}/ai/suggest-tags`, shows a spinner. On success:
  - If `provider_available === false`: disable the button with tooltip "No AI
    provider configured".
  - If `error !== null`: show inline error for 3 s.
  - If suggestions arrive: show a dismissible inline card listing `canonical` tags
    (already-known tags the AI matched) and `new_suggestions` (genuinely new).
    Each tag has an "Add" button that appends it to the confirmed-tags list in the
    same way the user would type/select it manually. Do NOT auto-apply any tag.

**Description step (where the user edits description):**
- Two small buttons: "Clean up (AI)" and "Summarize scrape (AI)".
  - "Clean up" calls `cleanup-description`; if `text` is returned, show it in a
    read-only preview box with "Use this" / "Discard" buttons. "Use this" replaces
    the draft description textarea contents (not a PATCH — just sets local state so
    the user can still edit before saving).
  - "Summarize scrape" calls `summarize`; same UX pattern.
  - Both buttons are disabled (with tooltip "No AI configured") if the last known
    `provider_available` was false. On fresh page load, probe by calling the endpoint
    once; cache the result in component state.
  - Never show these buttons if there is nothing to process (no description for
    cleanup; no scraped text for summarize — treat empty `description` on the session
    as nothing to clean).

**Key contract:** if AI is unavailable (no provider or call error), the wizard
functions identically to pre-Phase-8. AI buttons must not be on the critical wizard
path — they are supplementary.

### Surface 3 — AI suggestions in PendingTagsPage (tag admin)

**File:** `frontend/src/pages/admin/PendingTagsPage.tsx` (edit existing)

Add a lightweight "Get AI tag name suggestions" section at the top of
`PendingTagsPage`. This is for the tag-admin use case: the admin is reviewing
pending tags and wants AI to suggest what the canonical name should be, or whether
a pending tag looks like a duplicate.

UI:
- A text area pre-populated with all pending tag names (comma-separated; user can
  edit). A "Suggest canonical names (AI)" button.
- On click: the AI action is `POST /api/import-sessions/{id}/ai/suggest-tags` is NOT
  the right endpoint here (it requires an import session). Instead, build an
  **import-session–agnostic UI hint**: simply call `GET /api/tags?active_only=false`
  to get all tags and display a side-by-side "pending tags vs. existing canonical tags"
  list so the admin can spot duplicates/near-duplicates. The AI endpoint requires
  a session ID, which is not available here — so the "AI suggestions" on this page
  is actually a **smart filter** rather than an AI call: filter pending tags by
  similarity to existing canonical tags using client-side Levenshtein/fuzzy matching
  (`import-utils.ts` already has string helpers; add a `fuzzyMatchTags` function
  there). Show each pending tag alongside its closest existing canonical tag (if
  Levenshtein distance ≤ 3) as "possible duplicate of X".
- Show `provider_available` status from a cached `/api/import-sessions` probe only
  if there are no import sessions (when there is an active session, surface 2 covers
  the AI action better). The PendingTagsPage AI feature is a client-side smart-filter
  only (no AI endpoint call on this page).
- Clearly label this section "AI-assist: possible duplicates (client-side matching)".

### TypeScript + tests

- `npx tsc --noEmit` must pass with zero errors.
- Add vitest tests for any non-trivial pure logic (e.g. the Levenshtein / fuzzy-match
  helper in `import-utils.ts`, the `AiProvidersPage` query shapes).
- The existing vitest suite must remain green.

## Conventions to honor

- All imports from `@/` (`@/lib/api`, `@/context/AuthContext`, etc.) — never relative
  `../` across feature directories.
- Admin-gated pages import `useAuth` from `@/context/AuthContext`; render `null` or a
  redirect if `user.role !== 'admin'` (or use `AdminGuard` wrapper).
- TanStack Query keys follow the existing pattern: `['ai-providers']`, `['ai-providers', id]`.
- Mutation callbacks: `onSuccess` invalidates the relevant query key; `onError` sets
  inline error state.
- Inline transient feedback: `useState<string | null>(null)` for status message +
  `setTimeout(() => setStatus(null), 3000)` in the callback.
- No external form library; plain `useState` + controlled inputs.
- Delete buttons require an inline confirmation step (set `confirmDelete: id | null`
  in state; first click shows "Are you sure? [Confirm] [Cancel]" inline; confirm click
  fires the mutation). Pattern used in `UsersPage.tsx` (disable user) and
  `InvitesPage.tsx` (revoke).

## When done

1. Update this file's frontmatter (`status`, `completed`, one-line `result`).
2. `git mv` to `prompts/done/` (success) or `prompts/failed/` (failure).
3. No new `docs/decisions.md` entries required unless you make a non-obvious frontend
   decision; if so, add at top under a "Phase 8b frontend decisions" heading.
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the tree
   and report back with: complete file list (created/modified); proposed one-line `feat:`
   commit message; exact `npx tsc --noEmit` + vitest results; confirmation that the
   wizard and tag-admin pages still work with no AI provider configured.
