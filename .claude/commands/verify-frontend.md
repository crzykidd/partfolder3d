---
description: Run the canonical frontend verify gate (fresh tsc -b --force + npm run build + vitest run) and interpret the result
---

# Verify Frontend

Run the frontend gate and report whether it passed. Do NOT re-derive the recipe —
it lives in `scripts/verify-frontend.sh`.

## Run

```bash
./scripts/verify-frontend.sh
```

(Equivalently: `make verify-frontend`.) This `cd`s to `frontend/`, forces a
clean type-build (`tsc -b --force`), runs the real gate `npm run build`
(`tsc -b && vite build`), then `npx vitest run`.

## Interpret

- **Expected:** clean build, tests green — **≈333 tests**.
- **Two gotchas the script already handles — don't work around them:**
  - **Fresh build is REQUIRED.** `tsc -b` caches in `*.tsbuildinfo`; a stale
    cache HIDES real type errors (has bitten branch merges). The script forces
    `tsc -b --force` first — never trust an incremental build as the gate.
  - **Build, not typecheck.** The gate is `npm run build`, NOT
    `npx tsc --noEmit` — the latter uses the references-only root tsconfig and
    skips the strict settings the prod image enforces.
- **On failure:** report the exact failing step (type error / vite build error /
  a named test) and the error. Fix the underlying cause; do not bypass.
