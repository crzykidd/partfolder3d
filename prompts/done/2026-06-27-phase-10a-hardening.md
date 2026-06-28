---
name: 2026-06-27-phase-10a-hardening
status: done
created: 2026-06-27
model: sonnet
completed: 2026-06-28
result: SSRF guard added (ssrf_guard.py, wired into scraper + share-link import + URL import); migration 0010 adds 8 missing indexes; 31 new security tests added; 325→356 tests, 61%→63% coverage; ruff clean.
---

# Task: Phase 10a — Hardening (test coverage, security audit, perf/index audit)

Harden the now-feature-complete app (Phases 0–9) before v1. This is the **non-release** part of
**Phase 10** in [`docs/build-plan.md`](../docs/build-plan.md). Three workstreams:
**(1) test-coverage pass, (2) security audit + safe fixes, (3) performance/index audit.**

**Explicitly OUT OF SCOPE (do NOT do these):**
- **Do NOT cut a release, push to `main`, open a PR, or touch `.claude/commands/release-*`,
  CHANGELOG, or version files** — the orchestrator handles release engineering separately.
- **Do NOT do UI/UX polish or restyle pages** — a full UI revamp is coming separately (the owner
  is choosing a theme from the `/example1..3` prototypes). Leave `frontend/src/pages/examples/`
  alone.
- **Do NOT seed/benchmark 100k items** — instead do a static query/index audit (below) and
  document what real load-testing would need. No giant data generation.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) Phase 10, [`CLAUDE.md`](../CLAUDE.md),
  [`docs/decisions.md`](../docs/decisions.md), and [`PRD.md`](../PRD.md) §3.2/§8.5/§10/§11/§14
  for the security-sensitive contracts (atomic moves, share-link public/private separation,
  download privacy, encrypted secrets).
- **Deployment-readiness lesson:** several phases shipped code that crashed only when the stack
  actually ran. Favor tests that exercise real wiring (worker construction, startup, migrations,
  endpoint round-trips) over pure mocks.

## Working tree check

`git status --porcelain` — expect a clean tree on `dev`. Phase 9 is committed (`da49b50`).

## What to do

### 1. Test-coverage pass
- Measure coverage (`pytest --cov=app` for backend; note frontend vitest coverage if easy).
- **Add meaningful tests for gaps**, prioritizing: security-sensitive paths (auth, share-link
  public/private, download privacy, path traversal), the reconcile engine behaviors, the import
  commit→`create_item` path, backup archive contents, and any runtime-wiring not covered.
- Do NOT pad coverage with trivial asserts; target real risk. Report before/after coverage %.

### 2. Security audit + safe fixes
Audit (and fix the clearly-safe issues; report the rest with severity):
- **AuthN/Z**: every admin route admin-gated; per-user data scoped to the user; API-key auth.
- **Share links / public endpoints**: no private notes/records leak via public share or public
  ZIP or instance export (re-verify the Phase 7 contracts hold; add tests if thin).
- **Path traversal**: file download / item-file / staged-file endpoints confine to the intended
  dir (no `..`/symlink escape). Add tests.
- **SSRF**: the URL scraper + instance-share-link import fetch arbitrary user URLs — check for
  SSRF mitigations (block internal/link-local/metadata IPs) and the robots/ToS stance; add
  guards if missing (this is a real gap to look for).
- **Secrets**: provider keys / site tokens / instance key never logged or returned; backups
  contain secrets but live under `/data` only.
- **Injection**: confirm ORM/parameterized queries throughout (no string-built SQL); FTS inputs
  sanitized.
- Apply safe, in-scope fixes; for anything risky or large, write it up in the report + a
  `docs/decisions.md` note rather than half-fixing.

### 3. Performance / index audit (NO 100k seeding)
- Audit hot query paths for missing indexes and N+1 queries: catalog list/pagination + sort,
  FTS search, tag-filter joins (ItemTag), creator browse, favorites, jobs/issues lists, share
  audit. Confirm FK/filter/sort columns are indexed.
- **Add missing indexes via a new migration** (next number, **0010**) if you find gaps; keep it
  reversible (`upgrade`/`downgrade`). Fix obvious N+1s with eager loading where clearly correct.
- Document what true 100k-scale load-testing would require (a seeding harness) as a Phase-10
  follow-up — do not build it now.

## Conventions to honor

- Match existing structure; reuse fixtures. Backend changes only unless a test needs a tiny
  frontend touch (avoid frontend). **Do not restyle anything.**
- Verify locally: `ruff check backend/`, full `pytest` (with `--cov` if available),
  `alembic upgrade head` + `downgrade base` + re-upgrade (if you add migration 0010),
  `npx tsc --noEmit` (must stay clean if you touch any TS). **Bring up an ephemeral Postgres:**
  `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`,
  then `export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d"`,
  run migrations, then `pytest`. Recreate the scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone (PEP-668; `pip install -r backend/requirements.txt` + ruff/pytest + `pytest-cov`).
  Tear the container down when done.

## When done

1. Update frontmatter (`status`, `completed: 2026-06-27`, one-line result); `git mv` to
   `prompts/done/`.
2. `docs/decisions.md` entries (newest at top): security findings + fixes (and any deferred,
   with severity), indexes added (migration 0010), coverage before/after, the 100k-load
   follow-up note.
3. **You are a spawned agent: do NOT commit, push, or change branch.** Report back with: complete
   file list; proposed one-line `chore:`/`fix:`/`test:` commit message (pick the best fit; if the
   net change is mostly tests+indexes use `test:` or `chore(hardening):`); exact check results
   (ruff/pytest+count+coverage/alembic if 0010/tsc); a **security findings table** (issue,
   severity, fixed?/deferred); indexes added; and anything you could not verify.
