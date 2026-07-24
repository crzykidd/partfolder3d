# CLAUDE.md — PartFolder 3D

Agent guidance for this repository.

**On session start, read [`standards.md`](standards.md)** whenever your work could touch
anything the adopted standards govern (branching, commits, releases, handoff prompts).
It is the in-repo source of truth for which engineering standards this project conforms
to, and at which versions.

> **Status:** alpha (v0.7.2) — see [`README.md`](README.md) and [`PRD.md`](PRD.md).
> Full stack is built and shipping; v0.7.2 is the current release on `main`
> (v0.1.1–v0.7.2 tagged), with `dev` == `main` between releases.

## Operating model (project-specific)

PartFolder 3D is driven from a **central planning session** (a Claude session on
**Opus**):

- The planning session **plans, writes handoff prompts** (`prompts/`, per
  `handoff-prompt-workflow`), and **dispatches a spawned subagent on Sonnet** to execute
  each prompt end-to-end, then **reports back**. Execution is meant to be autonomous —
  the user does **not** babysit individual steps.
- **Approvals run automatically on `dev`.** This is a deliberate deviation from the
  `handoff-prompt-workflow` / `release-prep` "ask y/n before commit" rule: spawned agents
  prepare the working tree and the orchestrator **auto-commits on `dev`** with the correct
  conventional-commit prefix — no per-step y/n. Recorded in [`standards.md`](standards.md)
  and [`docs/decisions.md`](docs/decisions.md).
- **`main` stays protected — never direct-push.** The auto-commit freedom applies only to
  `dev`. Anything reaching `main` goes via PR (`code-checkin-and-pr`); releases go via
  `/release-prep` → merge → `/release-cut`.
- This environment is **not** sandbox-provisioned, so `repo-sandbox-permissions` is
  intentionally **not** adopted.

The operational rules below are pasted verbatim from each adopted standard.

---

## Verify before commit (durable rules)

Every code change is gated. The full recipe is encoded in `scripts/` — do **not**
re-paste it into prompts; call the scripts (or `make`) and interpret the result.

- **`make verify`** runs both gates. Or individually: **`make verify-backend`**
  (`scripts/verify-backend.sh` — ephemeral Postgres `pf3d-pg-v` on `:5433` →
  pinned ruff 0.8.4 → `alembic upgrade head` → `pytest -n auto`, ≈658 tests) and
  **`make verify-frontend`** (`scripts/verify-frontend.sh` — clean `tsc -b --force`
  → `npm run build` → `vitest run`, ≈333 tests). Slash: `/verify-backend`,
  `/verify-frontend`.
- **Two gotchas the scripts encode — never work around them:** backend tests
  **require `pytest -n auto`** (xdist gives each worker a fresh DB; a serial run
  reuses one DB → accumulated rows → spurious count failures); the frontend gate
  **requires a fresh build** (`tsc -b`'s incremental cache HIDES real type errors;
  the script forces `--force`).
- **The dev worker has NO hot-reload.** `uvicorn --reload` hot-reloads the
  backend, but the worker runs plain `python worker.py` — after any
  worker/task/scraper edit run **`make worker-restart`** (restarts the
  `worker` service in `docker-compose.dev.yml`).
- **Migration numbering is serialized.** A task that creates an Alembic migration
  must be run **one at a time** — the orchestrator assigns the next `00NN` number
  in the handoff prompt. Two parallel agents both creating `0023_*` is a
  guaranteed conflict.
- **Where things live:** [`docs/architecture.md`](docs/architecture.md) is the
  module map (feature → router / model / worker task / storage / api client /
  page / test file) plus the load-bearing technical gotchas. Consult it before
  grepping for where a feature's code lives.

---

<!-- Source: standards/code-checkin-and-pr @ v1.2.0 (crzynet/homelab-configs).
The full standard (publishing matrix, retention, CI check definitions) lives at:
https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards/code-checkin-and-pr/README.md -->

## Code check-in (operational rules)

This project adopts the `code-checkin-and-pr` standard. The full why-and-how lives at
the source above; the rules below are the per-session do/don'ts a coding agent must
honor by default:

- **Never push directly to `main`.** `main` is protected. All changes land via a pull
  request from `dev` → `main`, and only when every required check is green.
- **Day-to-day work happens on `dev`** (or a short-lived branch off `dev`). Push to
  `dev` freely.
- **Commit message prefixes are required** — Conventional-Commits style:
  - `feat:` — new user-facing feature
  - `fix:` — bug fix
  - `chore:` — config, tooling, dependencies, maintenance
  - `docs:` — documentation-only changes
- **Do not add `Co-authored-by:` trailers** unless the user explicitly asks.
- **Doc updates ship in the same commit as the code they describe** — never as a
  follow-up commit.
- **Never bypass hooks** (no `--no-verify`, `--no-gpg-sign`, etc.) unless the user
  explicitly asks. If a hook fails, fix the underlying issue.
- **Stable releases are tagged from `main` only.** Don't tag from `dev`.

If you're unsure whether an action would violate one of the above, stop and ask before
acting.

---

<!-- Source: standards/handoff-prompt-workflow @ v2.0.0 (crzynet/homelab-configs).
The full standard (the plan→decide→execute→document principle, model selection,
TEMPLATE, adoption checklist) lives at:
https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards/handoff-prompt-workflow/README.md -->

## Handoff prompts (operational rules)

This project adopts the `handoff-prompt-workflow` standard. The full why-and-how lives at
the source above; the rules below are the per-session do/don'ts an agent must honor by
default:

- **Edit-size threshold — decide by how much you'll change:**
  - A genuinely small change — roughly **one or two files and a few lines** (a typo, one
    config value, a one-line fix) — do it **in-session**, no prompt.
  - **Anything bigger requires a handoff prompt** — more than ~2 files, a multi-step
    change, a new feature, or any edit large enough that a fresh context would run it
    more cleanly. **When in doubt, write the prompt.**
- **A handoff prompt is a file in `prompts/`** — one per task, from `prompts/TEMPLATE.md`,
  with frontmatter (`name`, `status`, `created`, `model`, `completed`, `result`). Set
  `model:` from the task type: **Opus** for research/planning, **Sonnet** for coding;
  mixed defaults to Opus.
- **Execute the prompt by spawning a subagent — don't hand the user a command.** Spawn an
  agent on the prompt's `model:`, let it run the prompt end-to-end, and **report the
  outcome back**. The agent gets a fresh context; you stay in the loop.
  - **Manual fallback only on explicit request.** If the user says e.g. "use manual
    prompts for this," give them
    `claude --model <model> "Read prompts/<file>.md and execute it as your task."`
    instead of spawning.
- **Check the working tree before editing.** Run `git status --porcelain`, cross-reference
  the files the plan touches; if any have uncommitted changes, list them and ask before
  touching. Surface unrelated dirty files once; they don't block.
- **The prompt self-updates and moves when done.** The executing agent sets its
  frontmatter (`status`/`completed`/`result`) and `git mv`s the file into `prompts/done/`
  (success) or `prompts/failed/` (failure).
- **One commit at the end; the prompt bundles in.** The prompt file is **not** committed
  up front — it lands in the single end commit alongside the work and the prompt move.
  Propose ONE commit (files list + one-line message), ask `y/n`, stage only those specific
  paths. **Never `git add -A`, never auto-commit, never push.** A spawned agent prepares
  the tree and reports the proposed commit back; the orchestrating session surfaces the
  `y/n`.
- **Record non-obvious decisions** (approach changes, rejected alternatives, workarounds)
  in `docs/decisions.md`, newest at top.

If you're unsure whether an action would violate one of the above, stop and ask before
acting.

> **Project override:** per the [operating model](#operating-model-project-specific)
> above, the "ask `y/n`, never auto-commit" rule is relaxed **on `dev` only** — the
> orchestrator auto-commits prepared work with the right prefix so runs stay autonomous.
> `main` is never direct-pushed.

---

<!-- Source: standards/release-prep-and-cut @ v1.1.0 (crzynet/homelab-configs).
The full standard (two-phase prep/cut workflow, archive trigger, validation
steps, adoption checklist) lives at:
https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards/release-prep-and-cut/README.md -->

## Release process (operational rules)

This project adopts the `release-prep-and-cut` standard. The full why-and-how
lives at the source above; the rules below are the per-session do/don'ts a
coding agent must honor by default:

- **The version is stored BARE in the source-of-truth file** — no `v` prefix
  anywhere in code. The `v` prefix is added in exactly one place: the git tag
  and matching GitHub release name. Don't add it to README badges, CHANGELOG
  headers, in-code image tags, or anywhere else.
- **`CHANGELOG.md` is the single source of truth for release notes.** The PR
  description (set by `/release-prep`) and the GitHub release body (set by
  `/release-cut`) reuse the **same section verbatim**. Never author release
  notes twice.
- **One commit per release prep.** Version bump + changelog roll + every doc
  sync ship in a single `chore(release): prepare v<version>` commit. No
  `Co-authored-by:` trailers.
- **Never re-tag.** If `v<version>` already exists as a local tag, a remote
  tag, or a GitHub release, STOP. Never delete-and-recreate; never `--force`.
  Pick the next version instead.
- **`/release-cut` only after the PR has merged and CI is green.** The
  publish-to-`main` workflow must have already pushed `:latest` images to the
  registry before `/release-cut` runs. If you cannot confirm both — STOP and
  tell the user to wait.
- **The release tag is the only thing the cut command writes to `main`.** Both
  the prep commit and any follow-up docs commit land on `dev` and reach `main`
  only via PR. Never push directly to `main` as part of a release.

If you're unsure whether an action would violate one of the above, stop and
ask before acting.

> **Filled (Phase 10b):** the `/release-prep` and `/release-cut` commands in
> `.claude/commands/` have been updated with project-specific values — version file
> `backend/app/version.py` (+ `frontend/package.json` sync), image registry
> `ghcr.io/crzykidd/partfolder3d`, publish workflow `Build and publish Docker images`,
> local checks matching CI, and `docs/` as the changelog archive dir. The release
> commands are ready to use. See [`standards.md`](standards.md).
