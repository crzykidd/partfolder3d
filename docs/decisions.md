# Decisions

ADR-style log of non-obvious decisions, newest at top.

## 2026-06-27 — CI workflows added with tolerant-bootstrap guards; required-status-checks deferred

- Added four GitHub Actions workflows (`.github/workflows/ci.yml`, `codeql.yml`,
  `publish.yml`, `retention.yml`) modeled on the `filament-bridge` project's proven
  `code-checkin-and-pr` implementation.
- **Tolerant-bootstrap decision:** every job in `ci.yml` guards its real commands
  behind file/directory existence checks so the workflow passes cleanly on the current
  empty repo. Each guard is a placeholder to be removed per-job as scaffolding adds the
  corresponding piece (`backend/`, `frontend/`, `docker-compose.yml`, `Dockerfile`,
  alembic, etc.). The `publish.yml` Dockerfile guard works the same way.
- **Required-status-checks deferred:** branch-protection required-check wiring is
  intentionally deferred to after the first CI run completes and the check-run context
  names appear in GitHub's branch-protection UI. The orchestrator handles this wiring
  post-first-run.
- CI job names / check-run contexts for branch-protection wiring: `CI / Lint`,
  `CI / Config validation`, `CI / Migration check`, `CI / Compose validation`,
  `CI / Image build`, `CI / Test`, `CodeQL / Analyze (python)`,
  `CodeQL / Analyze (javascript-typescript)`.

## 2026-06-27 — Adopt three engineering standards; skip sandbox; autonomous dispatch model

- Adopted `code-checkin-and-pr` (1.2.0), `handoff-prompt-workflow` (2.0.0), and
  `release-prep-and-cut` (1.1.0). See [`standards.md`](../standards.md).
- **Skipped `repo-sandbox-permissions`**: this environment is not sandbox-provisioned, so
  the standard would be inert (it falls back to prompts with no friction reduction).
- **Operating model:** a central **Opus** planning session writes handoff prompts and
  dispatches autonomous **Sonnet** subagents. **Deviation from the standards'
  ask-before-commit rule:** the orchestrator **auto-commits on `dev`** with no per-step
  y/n — the user explicitly opted out of babysitting. `main` is never direct-pushed;
  everything reaches it via PR, and releases via `/release-prep` → merge → `/release-cut`.
- **`release-prep-and-cut` parked:** the slash-command templates are copied but their
  `<PLACEHOLDER>` values stay unfilled until a version file + CI exist (scaffolding).
- This adoption is the **final commit on `main`**; subsequent work moves to `dev`.
