# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** It carries the project-specific,
fast-moving context that does **not** live in `CLAUDE.md` (which holds the durable
standards/operating rules). Keep them separate: rules in `CLAUDE.md`, live state here.

> 🔄 **UPDATE THIS FILE BEFORE EVERY `/clear`.** Before clearing context, refresh the
> "Current status" and "Open threads" sections so the next session loses nothing. This is
> a deliberate ritual — see the checklist at the bottom.

**Last updated:** 2026-06-27

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

- **Phase:** 0 (not started). Next action = dispatch
  `prompts/2026-06-27-phase-0-scaffolding.md` (model: sonnet).
- **Branch:** `dev` (work here). `main` is protected.
- **Done so far:** PRD complete; brand assets in `docs/images/`; GH README; 3 standards
  adopted (code-checkin-and-pr 1.2.0, handoff-prompt-workflow 2.0.0, release-prep-and-cut
  1.1.0); CI workflows live (tolerant bootstrap) and green; `main` requires the 6 CI checks;
  build plan written.
- **No application code yet** — Phase 0 creates it.

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
