---
name: 2026-07-03-15-render-param
status: completed
created: 2026-07-03
model: sonnet
completed: 2026-07-03
result: Added render:"auto"|"off" param to single-commit and bulk-commit endpoints; tests pass
---

# Task: Add render preference to import-session commit API (issue #15 follow-up)

Add an optional `render: "auto" | "off"` parameter to the headless import commit paths
so callers can suppress server-side render enqueueing per-request (e.g. bulk migrations
that defer rendering to browser capture later).

## Before you start

- Read CLAUDE.md and standards.md for commit/branch rules.
- Check git status --porcelain before editing.

## Working tree check

Run `git status --porcelain` and confirm no unrelated dirty files before editing.

## What to do

1. Add `Literal` import + `CommitOptions` schema to `schemas.py`; add `render` field
   to `BulkCommitRequest`.
2. Add `render: str = "auto"` param to `_commit_session_inner`; gate `_enqueue_render`
   call on `render != "off"`.
3. Update `commit_import_session` to accept optional `CommitOptions` body.
4. Thread `body.render` through `bulk_commit_import_sessions`.
5. Add two tests to `test_bulk_import.py`: render=off skips enqueue, render=auto enqueues.
6. Update CHANGELOG.md [Unreleased] ### Added.
7. Record decision in docs/decisions.md (newest at top).

## Conventions to honor

- Conventional-commit prefix: `feat:`.
- No Co-authored-by trailers.
- `closes #15` in commit message (issue still open).
- Run ruff + pytest (scoped) before committing.

## When done

1. Update frontmatter: status=completed, completed=2026-07-03, result=one-line.
2. `git mv` this file to `prompts/done/`.
3. Record decisions in docs/decisions.md.
4. Commit all changed files in ONE commit with `feat:` prefix.
