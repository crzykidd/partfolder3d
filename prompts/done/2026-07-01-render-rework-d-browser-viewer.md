---
name: 2026-07-01-render-rework-d-browser-viewer
status: done
created: 2026-07-01
model: sonnet
completed: 2026-07-01
result: >
  Implemented in-browser 3D viewer (three.js + @react-three/fiber@8.18.0 +
  @react-three/drei@9.121.5, React 18 compatible). Created
  frontend/src/components/viewer/ModelViewer.tsx (lazy chunk); wired into
  DownloadsPanel.tsx via React.lazy + Suspense; 8 new vitest tests. All three
  gates green: tsc clean, 279 vitest pass, vite build pass. Code split confirmed:
  entry index-*.js ≈800 kB (no three.js), lazy ModelViewer-*.js ≈902 kB
  (three + fiber + drei). CHANGELOG.md and docs/decisions.md updated.
---

# Task: Frontend — in-browser live 3D viewer (three.js, code-split, size-capped)

Add an opt-in interactive 3D viewer so users can click an STL/OBJ (and under-cap 3MF geometry)
and rotate it in the browser. Phase D of the four-phase rework; assumes Phases A–C are
committed on `dev` (the "View in 3D" button + `FileOut.preview_3d` already exist).

## Before you start

- Read `docs/decisions.md` top entry (**2026-07-01 — Asset-detail / 3D-preview rework**) and
  `prompts/startnewsession.md`.
- **Frontend stack:** Tailwind + CSS-var theme + minimal Radix + lucide + TanStack Query +
  React Router; `apiFetch` CSRF wrappers; **no Mantine, no toast lib.**
- The "View in 3D" button + placeholder handler were added in Phase C; wire the real viewer to
  it. `FileOut.preview_3d` gates which files are viewable; raw files stream from
  `/api/items/{key}/files/{path}` (cookie-auth, same-origin — three's loaders fetch by URL and
  send same-origin credentials).

## Working tree check

`git status --porcelain`; ask before touching anything already dirty.

## What to do

1. **Deps**: add `three`, `@react-three/fiber`, `@react-three/drei` (pin versions). Confirm
   they're compatible with the project's React version.
2. **Lazy-loaded viewer** — a `ModelViewer` component loaded via `React.lazy` + `Suspense` so
   three.js is **code-split out of the main/catalog bundle**. Verify the split in the
   `vite build` chunk output (three must be its own chunk, not in the entry chunk).
3. **Viewer implementation** (react-three-fiber + drei):
   - Load geometry with three's `STLLoader` / `OBJLoader` / `3MFLoader` (from
     `three/examples/jsm/...`) by file extension, fetching the raw file URL.
   - `OrbitControls` (rotate/zoom/pan), auto-fit/center (drei `Bounds` / `Center`), a
     two-light setup + neutral material, background matching the app theme (light/dark via the
     CSS-var theme). Show a loading state and a graceful error state.
4. **Wire it up**: clicking "View in 3D" opens the viewer (modal or inline canvas) for the
   selected file. Only offered when `preview_3d === true`; for over-cap files show the static
   thumbnail with a "too large for in-browser preview" note (no button). Clean up the
   WebGL context on unmount (dispose geometry/renderer) to avoid leaks when opening several.

## Conventions to honor

- **Changelog:** `CHANGELOG.md [Unreleased]` (Added: in-browser 3D viewer).
- **Verify (all three gates):** `tsc`, `vitest` (test the gating/lazy-wrapper logic — the
  WebGL canvas itself needn't render in jsdom; guard/mocking is fine), and **`npx vite build`**
  — confirm it passes AND that three is a separate lazy chunk (report the chunk sizes).
- Keep the viewer chunk from bloating the initial load — lazy import is mandatory, not
  optional.

## When done

1. Frontmatter (`status`/`completed`/`result`), then `git mv` into `prompts/done/` or
   `prompts/failed/`.
2. Record non-obvious decisions in `docs/decisions.md`.
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run all three frontend gates
   (report the chunk split), and report back the paths to stage + a one-line
   conventional-commit message + verification results. Orchestrator auto-commits on `dev`.
   Never `git add -A`.
