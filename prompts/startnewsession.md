# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** It carries the project-specific,
fast-moving context that does **not** live in `CLAUDE.md` (which holds the durable
standards/operating rules). Keep them separate: rules in `CLAUDE.md`, live state here.

> 🔄 **UPDATE THIS FILE BEFORE EVERY `/clear`.** Before clearing context, refresh the
> "Current status" and "Open threads" sections so the next session loses nothing. This is
> a deliberate ritual — see the checklist at the bottom.

**Last updated:** 2026-06-27 (Phase 5 complete)

---

## Session start order

1. **This file** — current state + gotchas.
2. **`CLAUDE.md`** — operating model + adopted-standard rules (auto-read per its own pointer).
3. **`standards.md`** — which standards/versions apply.
4. **`docs/build-plan.md`** — the phased roadmap; find the current phase.
5. **The current phase's prompt** in `prompts/` — the next executable handoff.

## Operating model (recap — full version in `CLAUDE.md`)

- This is the **central Opus planning session**. It **plans, writes handoff prompts**
  (`prompts/`), and **dispatches autonomous Sonnet subagents** to execute them, then
  reports back. The user does **not** babysit.
- **Auto-commit on `dev`** (no per-step y/n) with conventional prefixes. **`main` is
  PR-only / never direct-pushed.**
- Bigger-than-1–2-file changes → write a prompt + dispatch; don't do them inline.

## Current status

- **Phase:** 5 **complete** (5a `2b44ddd` + 5b `2d032cf` on `dev`). Next action = plan +
  dispatch **Phase 6 — Reconciliation / scan engine** (write `prompts/2026-06-27-phase-6-*.md`,
  model: sonnet; see build-plan §"Phase 6" + PRD §8).
- **Branch:** `dev` (work here). `main` is protected. Nothing pushed/PR'd yet (no dev→main
  until a working product exists).
- **Done so far:** Phases 0–5 committed on `dev`:
  - **0** scaffolding/dev loop; **1** identity/first-run/settings; **2** libraries/storage/
    sidecar/item core (atomic rename); **3** catalog UI (FTS, tag cloud, browse, item page,
    file/ZIP downloads); **4** worker jobs + mesh rendering + job/scheduled-jobs monitor UI;
    **5a** import-wizard **backend** (ImportSession staging, URL scraper, site-capabilities +
    encrypted tokens, tag reconciliation/approval, inbox scheduled-scan, commit→`create_item`);
    **5b** import-wizard **frontend** (Add Asset modal, `/import/:sessionId` wizard, `/imports`
    list, site-setup prompt, `/admin/pending-tags`). All checks green (189 pytest, tsc, 82 vitest).

## Phase 5 follow-ups (small; fold into a later phase)

- **`TagSummary` lacks a `status` field**, so the frontend can't distinguish pending vs. active
  tags — `/admin/pending-tags` lists ALL tags (Approve is idempotent, so it's safe but noisy).
  Add `status` to `TagSummary` + filter the page to pending-only. Good Phase 6 cleanup.
- **No `GET /api/items/by-id/{id}`** — committed-session deep-links fall back to `/catalog`
  instead of the new item. Minor; add if a by-id lookup is otherwise needed.
- **Verification gotcha (closed):** the 5a agent had no Postgres, so it could only run 6 pure
  unit tests. The orchestrator spun up an ephemeral PG (docker `postgres:16-alpine` on `:5433`,
  user/pass/db `partfolder3d`/`testpass`/`partfolder3d`) and caught **2 real bugs**: invalid
  `CREATE TYPE IF NOT EXISTS` in migration 0006 (→ `DO`-block guard) and missing
  `python-multipart` dep (app wouldn't boot). After fixes: **189 pytest passed**, alembic
  up/down/up clean, ruff/tsc/vitest green. **Lesson: bring up an ephemeral PG to verify any
  migration/DB work before committing.**
- **Phase 4 recovery note:** the Phase 4 agent hard-crashed before its verify/commit step; no
  git loss; resumed + verified + fixed 3 `render_mesh.py` bugs. Render spike **go**
  (pyrender+OSMesa CPU-only).

## Phase 4 follow-ups to confirm later (need Docker/CI, not verifiable here)

- pyrender+EGL path (Dockerfile installs `libegl1`/`libgbm1`) and OSMesa **inside** the image.
- End-to-end render wiring (item create → render job → `renders/<sha256>.png`) needs the full
  compose stack (arq worker + Redis).
- VTK offscreen does **not** work on a stock CPU host (Xlib SIGABRT); kept in the detect chain
  only for EGL/OSMesa-built VTK. See `docs/decisions.md` Phase 4 entries.

## Repo & remotes

- **Code:** GitHub [`crzykidd/partfolder3d`](https://github.com/crzykidd/partfolder3d).
  `main` protected (PRs required, 6 CI checks, no direct push). Work on `dev`.
- **Registry:** `homelab-configs` on **Gitea** (`gitea.crzynet.com`) — separate repo,
  separate remote. Its `projects/partfolder3d/` entry is committed locally but **not yet
  pushed** (see Open threads).
- `gh` is authenticated as `crzykidd`.

## Environment gotchas

- **No sandbox here** — `repo-sandbox-permissions` was intentionally not adopted, so bash
  may prompt unless the session runs in an auto-approve mode. (User runs it auto so agents
  aren't babysat.)
- **Image processing needs a venv** — system Python is PEP-668 externally-managed (pip
  blocked). A scratchpad venv with Pillow/numpy/scipy/pyyaml exists under the session
  scratchpad; recreate if gone.
- **External port `8973`** (nginx) — changeable in `docker-compose.yml`.
- **Brand colors:** teal `#0FA4AB`, navy `#091D35`. Source logo PNGs in `private_data/`
  (gitignored). Locked logo style: **flat icon, both modes** (dark = navy flat recolored
  light).

## Key file map

| Path | What |
|---|---|
| `PRD.md` | Authoritative product spec (§1–18). |
| `docs/build-plan.md` | Phased roadmap + locked build-time tech decisions. |
| `docs/decisions.md` | ADR-style decision log (newest at top). |
| `CLAUDE.md` | Operating model + adopted-standard snippets. |
| `standards.md` | Adopted standards + pinned versions + deviations. |
| `prompts/` | Handoff queue; `prompts/done/` + `prompts/failed/` archives. |
| `.claude/commands/release-{prep,cut}.md` | Release slash commands (parked; placeholders unfilled). |
| `.github/workflows/` | CI (`ci`, `codeql`, `publish`, `retention`). |
| `docs/images/` | Brand assets + usage README. |

## Open threads (carry these forward)

- [x] **`homelab-configs` registry entry pushed** to Gitea by the user (2026-06-27).
- [ ] **After Phase 0 CI is green:** add `CodeQL / Analyze (python)` +
      `CodeQL / Analyze (javascript-typescript)` to `main` required status checks (deferred
      because CodeQL errors on an empty source tree).
- [ ] **Remove remaining CI bootstrap guards** per-piece as later phases add them.
- [ ] **`release-prep`/`release-cut` placeholders** stay parked until a version file + CI
      exist (Phase 0 adds the version file; fill at first release).
- [ ] **PRD §18 remaining notes** to honor when their phase arrives: instance-encryption-key
      provisioning/rotation (Phase 1), move journaling/crash recovery (Phase 2/6), title
      sanitization (Phase 2).

## Before-`/clear` checklist

1. Update **Last updated** date + **Current status** (phase, what just finished, next action).
2. Update **Open threads** (tick done, add new).
3. Ensure any in-flight handoff prompt's frontmatter + `prompts/done|failed/` placement is
   correct, and decisions went into `docs/decisions.md`.
4. Confirm work is committed on `dev` (and note anything intentionally uncommitted here).
