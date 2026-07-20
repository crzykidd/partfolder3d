---
name: 2026-07-19-3mf-preload-size-guard
status: done          # pending | in-progress | done | failed
created: 2026-07-19
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-07-19
result: >
  Added ANALYZE_MAX_3MF_XML_MB (default 256) + _check_3mf_xml_size pre-load guard in
  mesh_analysis.py, threaded through analyze_file/_analyze_3mf/run_analyze_subprocess/
  analysis.py (both call sites); reuses the existing MeshTooLargeError -> __CAP_SKIP__ ->
  AnalyzeCapSkip -> low-confidence stub chain. make verify-backend green (878 passed).
---

# Task: Pre-load size guard for oversized 3MF geometry (extends issue #37 fix #4)

Issue #37 fix #4 added a triangle-count cap, but it runs AFTER `trimesh.load`. A 3MF whose
geometry is enormous can't even be loaded: trimesh parses each `3D/Objects/*.model` part
into an lxml DOM, and a ~500 MB geometry-XML part balloons past 8 GB — so under the analyze
subprocess's 4 GB RLIMIT it fails (clean, worker survives, but the file is never analyzed
and re-fails on every rescan). **Live-diagnosed example:** `Dahlias+3MF+Complete.3mf` is
1.09 GB uncompressed with two `3D/Objects/object_*.model` parts at ~505 MB each.

Add a **cheap pre-load guard**: read the 3MF's part sizes from the ZIP central directory
(no decompression) and, if the total geometry-XML is too large to safely parse, raise the
existing `MeshTooLargeError` BEFORE calling trimesh — so the file becomes a cached
low-confidence "too large" stub (exactly like the triangle cap) instead of a doomed
multi-GB parse that fails and retries forever.

**Scope: this pre-load 3MF size guard only.** It's a small hardening that ships in the
upcoming v0.6.1 alongside the four #37 fixes already on `dev`. Do NOT touch the color
parser's huge_tree behaviour or anything else. This is a `dev`-branch autonomous run.

## Before you start

- Read `CLAUDE.md` (verify gates; worker no hot-reload).
- **Read `backend/app/worker/mesh_analysis.py`** — especially `MeshTooLargeError` (already
  defined, ~line 70), `_check_triangle_cap` (~line 344), and `_analyze_3mf` (~line 383,
  which already does `raw_bytes = path.read_bytes()` then `trimesh.load`). Your guard goes
  at the TOP of `_analyze_3mf`, before the trimesh load.
- **Read `backend/app/config.py`** around the `ANALYZE_*` settings (added by the prior #37
  work: `ANALYZE_TIMEOUT_S`, `ANALYZE_MEM_LIMIT_MB`, `ANALYZE_MAX_TRIANGLES`) — add the new
  setting next to them, and mirror it into `.env.example`.
- **No Alembic migration**, no schema change.

## Design / rationale (follow this)

- **Why uncompressed size, read from the ZIP directory:** `zipfile.ZipFile(path).infolist()`
  exposes each entry's `file_size` (uncompressed) WITHOUT decompressing — O(1)-ish, no memory
  cost. Summing the geometry parts gives a reliable pre-load proxy for how big the lxml DOM
  will get.
- **Which parts count:** the 3MF geometry lives in `3D/3dmodel.model` AND `3D/Objects/*.model`
  (case-insensitive match on names ending `.model` under `3D/`). Sum those entries'
  `file_size`. Ignore thumbnails / metadata / textures.
- **Threshold:** add `ANALYZE_MAX_3MF_XML_MB: int = 256`. Rationale to record: a ~505 MB part
  blew past 8 GB when parsed, i.e. the lxml tree is ~15-20× the XML bytes; 256 MB total keeps
  the worst-case tree within the 4 GB `ANALYZE_MEM_LIMIT_MB` bound with headroom. Tunable via
  env. (Do NOT hard-tie it to `ANALYZE_MEM_LIMIT_MB` — keep it an independent knob, but
  mention the relationship in the comment.)
- **Behaviour when over the threshold:** raise `MeshTooLargeError` with a clear message
  (e.g. `f"{path.name}: 3MF geometry is {total_mb:.0f} MB uncompressed (cap {cap} MB) —
  skipping analysis"`). The existing subprocess wrapper already converts `MeshTooLargeError`
  → `__CAP_SKIP__` → `AnalyzeCapSkip` → the low-confidence stub in `_analyze_item_body`, so
  you get the cached "too large" state for free — verify that chain still works for this new
  raise site.

## What to do

1. **Config:** add `ANALYZE_MAX_3MF_XML_MB: int = 256` in `backend/app/config.py` next to the
   other `ANALYZE_*` settings, with a comment explaining the pre-load-guard rationale. Add a
   matching commented block to `.env.example` mirroring the style of the other `ANALYZE_*`
   entries.
2. **Guard:** in `backend/app/worker/mesh_analysis.py`, add a small helper (e.g.
   `_check_3mf_xml_size(path, max_xml_mb)`) that opens the ZIP, sums the `.model` part
   `file_size`s under `3D/`, and raises `MeshTooLargeError` when the total exceeds the cap.
   Call it at the START of `_analyze_3mf` — BUT only when a cap is in effect. Thread it like
   the triangle cap: `_analyze_3mf` already receives `max_triangles`; add a parallel
   `max_3mf_xml_mb: int | None = None` param (None = no guard, preserving existing direct
   callers/tests). `analyze_file` passes it through, defaulting to None so current callers are
   unaffected; the subprocess runner (`run_analyze_subprocess`) passes
   `settings.ANALYZE_MAX_3MF_XML_MB`.
   - Update `backend/app/worker/analyze_subprocess.py`: add a `max_3mf_xml_mb` param to
     `run_analyze_subprocess` + the child `_analyze_worker`, and pass it into `analyze_file`.
   - Update `backend/app/worker/tasks/analysis.py`: pass
     `max_3mf_xml_mb=settings.ANALYZE_MAX_3MF_XML_MB` at BOTH `run_analyze_subprocess` call
     sites (the unsliced-3MF branch and the generic branch — the generic branch is only STL/
     OBJ/PLY so the 3MF guard is a no-op there, but pass it uniformly for consistency; the
     guard only fires inside `_analyze_3mf`).
   - Be defensive: if the ZIP can't be opened / read for the size check, do NOT raise the cap
     error — log a debug/warning and fall through to the normal load (a corrupt-zip failure
     should surface as a real analysis error, not a spurious "too large" skip).
3. **Tests** (mirror the existing cap tests in `backend/tests/test_object_analysis.py` and
   the subprocess tests in `backend/tests/test_analyze_subprocess.py`):
   - A small real 3MF fixture with `max_3mf_xml_mb=0` (or a tiny cap) raises `MeshTooLargeError`;
     with `max_3mf_xml_mb=None` (or a generous cap) it analyzes normally.
   - The cap-skip chain end-to-end via `run_analyze_subprocess` (tiny `max_3mf_xml_mb`) →
     `AnalyzeCapSkip` (and, if you add a body-level test, the low-confidence stub is stored).
   - The defensive path: a non-ZIP / unreadable file does NOT raise the size-cap error (it
     falls through to the normal error path). Keep fixtures tiny; no giant files.
4. **CHANGELOG.md** — add a `### Fixed` (or extend the existing #37 mesh-guard bullet) under
   `[Unreleased]` in the SAME commit, e.g.:
   `- Very large 3MF files are now detected by uncompressed geometry size and skipped
   (low-confidence) before trimesh attempts a multi-GB parse, so a huge multi-object 3MF is
   cached as "too large" instead of failing analysis on every rescan (issue #37).`

## Verify

- `make verify-backend` MUST be green. Iterate until it passes; report final pass/fail + count.
  No frontend changes → no `verify-frontend`.
- Do NOT restart the live worker/stack — the orchestrator will re-run the live check after commit.

## Conventions to honor

- Match surrounding style in `mesh_analysis.py` / `analyze_subprocess.py`. `# noqa: PLC0415`
  deferred imports. Conventional-commit prefix `fix:`. Reference `(issue #37)` — do NOT add a
  `closes` (the four-fix commit `f037e64` already carries `closes #37`). No `Co-authored-by:`.
  Changelog ships in the same commit.

## When done

1. Update frontmatter (`status`/`completed`/`result`).
2. `git mv` this file into `prompts/done/` (or `prompts/failed/`).
3. Prepend the decision to `docs/decisions.md` (why a PRE-load uncompressed-size guard is
   needed on top of the post-load triangle cap; the ~15-20× XML→DOM blow-up finding; the
   256 MB default rationale; defensive fall-through on unreadable ZIP).
4. **You are a spawned agent: do NOT commit and do NOT push.** Prepare the working tree, then
   report back: (a) exact file list (incl. prompt move), (b) a one-line `fix:` commit message
   referencing `(issue #37)`, (c) the `make verify-backend` result, (d) any deviations.
