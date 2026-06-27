# Standards implemented

This project implements the following [standards](https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards)
from the crzynet `homelab-configs` repo. Each row pins the **version** this project has
actually wired up.

| Standard | Version | Adopted | Notes |
|---|---|---|---|
| [code-checkin-and-pr](https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards/code-checkin-and-pr/README.md) | 1.2.0 | 2026-06-27 | Branch strategy (`dev`/protected `main`) + commit conventions + `CLAUDE.md` snippet **in effect now**. CI workflows (`ci.yml`, `codeql.yml`, `publish.yml`, `retention.yml`) **committed as tolerant bootstrap** — each job passes on the empty repo and auto-enforces as scaffolding adds each piece (remove existence guards per-job). Branch-protection required-status-checks wiring is **deferred to post-first-run** (orchestrator handles after check-run contexts appear in GitHub's UI). **Deviation:** auto-commit on `dev` (no per-step y/n) per the project operating model; `main` stays PR-only. No `Co-authored-by:` trailers. |
| [handoff-prompt-workflow](https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards/handoff-prompt-workflow/README.md) | 2.0.0 | 2026-06-27 | `prompts/` + `prompts/TEMPLATE.md` + `docs/decisions.md` in place; `CLAUDE.md` snippet pasted. **Deviation:** the central Opus session dispatches autonomous **Sonnet** subagents and the orchestrator **auto-commits on `dev`** instead of asking y/n — the user opted out of babysitting. Manual-fallback launch command is unused by default. |
| [release-prep-and-cut](https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards/release-prep-and-cut/README.md) | 1.1.0 | 2026-06-27 | `/release-prep` + `/release-cut` templates copied to `.claude/commands/`; `CLAUDE.md` snippet pasted. **Parked:** placeholders (`<VERSION_FILE>`, `<LOCAL_CHECKS>`, `<DOCS_TO_SYNC>`, workflow + image-tag names) are filled at scaffolding / first release once the version file + CI exist. Composes with `code-checkin-and-pr`. |

## Not adopted

- **repo-sandbox-permissions** — intentionally skipped; this environment is **not**
  sandbox-provisioned, so the standard would be inert.
- **vexp-context-engine** — deprecated/sunset; do not adopt.
