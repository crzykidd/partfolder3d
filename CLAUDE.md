# CLAUDE.md — PartFolder 3D

Agent guidance for this repository.

**On session start, read [`standards.md`](standards.md)** whenever your work could touch
anything the adopted standards govern (branching, commits, releases, handoff prompts).
It is the in-repo source of truth for which engineering standards this project conforms
to, and at which versions.

> **Status:** design/planning phase — see [`README.md`](README.md) and [`PRD.md`](PRD.md).
> No application code yet; scaffolding is the next milestone.

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

> **Parked until scaffolding:** the `/release-prep` and `/release-cut` commands in
> `.claude/commands/` still contain `<PLACEHOLDER>` values (version file, local checks,
> docs to sync, workflow + image-tag names). They are filled once the app's version file
> and CI exist. See [`standards.md`](standards.md).
