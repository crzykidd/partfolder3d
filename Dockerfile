# PartFolder 3D — backend + worker image
# ghcr.io/crzykidd/partfolder3d
#
# Multi-stage build; CPU-only (no GPU drivers).
# The worker service overrides CMD to "python worker.py".

# ---- base: Python runtime ----
FROM python:3.12-slim AS base
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ---- deps: install Python packages (cached layer) ----
FROM base AS deps
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- runtime: copy application source ----
FROM deps AS runtime
# Copy backend source into /app so imports resolve as `from app.xxx import ...`
COPY backend/app/ ./app/
COPY backend/worker.py ./
COPY backend/alembic.ini ./
COPY backend/alembic/ ./alembic/

# Data directory will be mounted at runtime (./data:/data in compose)
RUN mkdir -p /data

# Default: run the FastAPI API server.
# The `worker` compose service overrides this to: python worker.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
