# PartFolder 3D — thin convenience targets. The real recipes live in scripts/.
.PHONY: verify verify-backend verify-frontend worker-restart

## verify: run both backend and frontend gates
verify: verify-backend verify-frontend

## verify-backend: ephemeral PG :5433 + pinned ruff + alembic + pytest -n auto
verify-backend:
	./scripts/verify-backend.sh

## verify-frontend: fresh tsc -b --force + npm run build + vitest run
verify-frontend:
	./scripts/verify-frontend.sh

## worker-restart: restart the dev worker (it has NO hot-reload — do this after
##   any worker/task/scraper edit; uvicorn backend hot-reloads, the worker does not)
worker-restart:
	docker compose -f docker-compose.dev.yml restart worker
