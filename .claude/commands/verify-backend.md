---
description: Run the canonical backend verify gate (ephemeral PG + pinned ruff + alembic + pytest -n auto) and interpret the result
---

# Verify Backend

Run the backend gate and report whether it passed. Do NOT re-derive the recipe —
it lives in `scripts/verify-backend.sh`.

## Run

```bash
./scripts/verify-backend.sh
```

(Equivalently: `make verify-backend`.) This ensures an ephemeral Postgres
container `pf3d-pg-v` on host `:5433`, runs the pinned linter
(`backend/.venv/bin/ruff` — 0.8.4 + `backend/pyproject.toml`), applies
`alembic upgrade head`, then runs `pytest -n auto`. The container is left
running for reuse; pass `--teardown` to remove it.

## Interpret

- **Expected:** lint clean, migrations at head, suite green — **≈658 tests**.
- **Two gotchas the script already handles — don't work around them:**
  - **xdist is REQUIRED.** Tests run `-n auto`; each worker gets a fresh
    per-worker DB. A serial run reuses one DB → committed rows accumulate →
    spurious count-assertion failures. Never "fix" a count failure by running
    serially.
  - **Pinned ruff only.** Use the script's `backend/.venv/bin/ruff` — an
    unpinned/no-config ruff throws false UP042/F841 that CI does not.
- **On failure:** report the exact failing step (lint / migration / a named
  test) and the error. Fix the underlying cause; do not bypass.
- If Docker isn't available or the container can't start, say so — the backend
  suite needs Postgres.
