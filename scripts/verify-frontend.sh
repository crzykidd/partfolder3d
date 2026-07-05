#!/usr/bin/env bash
#
# verify-frontend.sh — canonical frontend verify recipe for PartFolder 3D.
#
# Steps (run from frontend/):
#   1. FRESH type-build — `tsc -b --force` (defeats the incremental cache).
#   2. `npm run build` (tsc -b && vite build) — the real prod-shaped gate.
#   3. `npx vitest run` (~333 tests).
#
# GOTCHA (tsc incremental cache): `tsc -b` caches results in *.tsbuildinfo. A
# stale cache HIDES real type errors that a clean build would surface (this has
# bitten merges of two worktree branches). We force a clean type-build first so
# type errors always show.
#
# GOTCHA (build, not typecheck): the gate is `npm run build`, NOT
# `npx tsc --noEmit` — the latter uses the references-only root tsconfig and
# skips the strict project-reference settings the prod image enforces.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/frontend"

echo "==> [1/3] Clean type-build (tsc -b --force — defeats stale incremental cache)"
npx tsc -b --force

echo "==> [2/3] Production build (npm run build = tsc -b && vite build)"
npm run build

echo "==> [3/3] Frontend tests (vitest run)"
npx vitest run

echo "frontend verify: OK"
