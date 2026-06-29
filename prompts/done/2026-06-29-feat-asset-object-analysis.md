---
name: 2026-06-29-feat-asset-object-analysis
status: done
created: 2026-06-29
model: sonnet
completed: 2026-06-29
result: >
  Implemented Phase 16 end-to-end: mesh_analysis module (analyze_file, _parse_3mf_colors,
  watertight fallback, volume formula), migration 0016 (object_analysis JSONB + 2 settings),
  worker task analyze_item (sha-keyed cache, best-effort per-file), items router
  (FileOut.object_analysis, ItemDetail aggregate, _enqueue_analyze on create/rescan), frontend
  types + ItemPage ObjectBreakdownSection with swatches/dims/LOW CONF. All checks pass: ruff
  clean, 12/12 pytest (object analysis) + full suite green, tsc clean, 198/198 vitest, vite build
  succeeds. Migration verified on ephemeral postgres:16-alpine.
---

# Task: Per-object asset analysis — colors + estimated filament grams from the STL/3MF files

Statically analyze an item's **model files** (independent of any print log) to report, **per object**:
**how many colors** and an **estimated grams of filament**. Runs in the worker like rendering.
Owner decisions: **grams = volume estimate now** (designed so a real slicer can replace it later);
**colors = standard 3MF materials + STL=1 + best-effort Bambu/Orca painted**.

## Reality / approach (important — set expectations in the UI)
- **Objects**: an STL = one object; a 3MF can contain **multiple objects/meshes**. Use `trimesh`
  (already a dep) to load each model file — for a 3MF, `trimesh.load(...)` yields a `Scene` whose
  `.geometry` dict is the objects; an STL is a single mesh. Analyze each object.
- **Estimated grams** (per object): `grams = volume_cm3 × density × infill_factor`.
  - `volume_cm3` from `trimesh` (`mesh.volume`, use `abs`). Many meshes aren't watertight →
    volume is unreliable; detect `mesh.is_watertight`, attempt a light repair
    (`mesh.fill_holes()` / `trimesh.repair`), and if still not watertight fall back to the convex
    hull volume **and flag low confidence**. Never crash — best-effort per object.
  - `density` (g/cm³) + `infill_factor` come from **configurable instance settings** (defaults:
    density **1.24** [PLA], infill **15%** → factor accounts for walls+infill; keep the formula
    simple and documented). Store the method used as `estimate_method='volume'` so a future
    `'sliced'` method can replace it without schema change.
  - **Clearly an estimate** — the UI must label it and note the assumptions; it can be 2–5× off.
- **Colors** (per object):
  - **STL** → always **1**.
  - **3MF standard** → parse the 3MF zip's model XML (`3D/3dmodel.model`) with **`lxml`** (already a
    dep): count distinct materials/colors from `<basematerials>` / color-group / `<m:colorgroup>` /
    multiproperties assigned to the object's triangles/object. (You may use `lib3mf` if it clearly
    helps standard materials — but it does NOT cover vendor paint, and adding a dep needs a good
    reason; prefer lxml. If you add `lib3mf`, justify it in the report.)
  - **Bambu/Orca painted 3MF (best-effort)** → these store per-face paint as **vendor-specific**
    attributes (e.g. `paint_color` / `mmu_segmentation` on `<triangle>` elements, or color data in
    the project's extra files inside the zip). Best-effort: count distinct paint values per object.
    If a variant isn't recognized, fall back to the standard count (don't fail). Note clearly in
    code + report that this is heuristic and may miss variants.
  - Record the distinct color **hex values** when available (raw hex only — no name-matching).

## Working tree check
`git status --porcelain` clean on `dev`.

## Data model — migration 0016
- Store analysis per **File** (model files). Add to `File` (or a small dedicated table if cleaner):
  `object_analysis` (JSONB, nullable) = `{ analyzed_at, source_hash, objects: [ { name, color_count,
  colors: [hex...], volume_cm3, est_grams, est_method, watertight: bool, low_confidence: bool,
  dims_mm: [x,y,z] } ], total_objects, total_colors, total_est_grams } `. Key it to the file's
  `sha256` (re-analyze only when the file changes).
- Instance settings for the estimate: `estimate_filament_density_g_cm3` (default 1.24) and
  `estimate_infill_pct` (default 15) — via the existing settings mechanism (admin-editable).
- `alembic upgrade head` must pass; document downgrade.

## Worker
- Add an `analyze_item` arq task (or fold into the existing per-item flow next to rendering): for
  each model `File` (role=model, parseable mesh extension — stl/3mf/obj/ply), load with trimesh,
  analyze each object as above, write `object_analysis` keyed by the file's sha256. Skip if the
  stored analysis matches the current sha256 (cache, like renders). Best-effort, wrapped so one bad
  file doesn't fail the whole item. Enqueue it where renders are enqueued (item create / file
  change / the per-item **Rescan** path) so it stays fresh.

## API
- Expose per-file `object_analysis` in `ItemDetail` (and an item-level aggregate: total objects,
  total distinct colors, total estimated grams). Don't block the response if analysis is missing
  (null = not yet analyzed).

## UI (`frontend/src/pages/ItemPage.tsx`)
- A clear **"Object breakdown"** section: per object → color count (with small swatches when hex is
  known), estimated grams, and dims; plus an item total (objects / colors / est. grams). **Label the
  grams as an estimate** with a short tooltip/footnote stating the density + infill assumptions and
  that real values need slicing. Mark low-confidence (non-watertight) objects. Aurora-styled, feature
  parity for the rest of the page. Add api.ts types.

## Out of scope (state in report)
- Real slicing for accurate grams/colors (the `est_method='sliced'` upgrade) — future, the schema is
  ready for it.
- Print-log gcode multi-filament parsing — separate/earlier idea, not this task.

## Verify
- Backend: `ruff check backend/`; **ephemeral Postgres** for migration 0016 + tests (docker
  one-liner; `alembic upgrade head`; `pytest`; tear down; recreate the scratchpad venv at the
  session path if gone). Tests with **real small fixtures**: a generated STL (trimesh box) → 1
  object, 1 color, est_grams ≈ volume×density×infill; a 3MF with ≥2 materials → correct color count
  + per-object volumes; a malformed/non-watertight mesh → degrades with low_confidence, no raise.
  (Create fixtures programmatically via trimesh where possible; for a multi-material 3MF, a tiny
  hand-authored 3MF fixture is fine.)
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite build`
  MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: volume-estimate formula + settings, the watertight fallback, 3MF color
   parsing (standard via lxml + best-effort vendor paint), est_method field for future slicing,
   per-file sha-keyed cache.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / alembic 0016 / tsc / vitest / **vite
   build**); migration-restart note; which color cases work vs best-effort; an example analysis of a
   sample file; what's deferred to the slicing upgrade; anything unverified.
