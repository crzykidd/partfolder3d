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
# Render thread caps — limit CPU saturation on multi-core hosts.
# Driven by RENDER_CPU_THREADS (default 2); the worker startup hook also
# enforces these at runtime.  Overridden per-service in docker-compose.
ENV OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    VECLIB_MAXIMUM_THREADS=2 \
    NUMEXPR_NUM_THREADS=2 \
    LP_NUM_THREADS=2

# ---- deps: system libraries + Python packages (cached layer) ----
FROM base AS deps

# System libraries for headless rendering (render-rework-A: VTK-only stack).
# The `vtk-osmesa` wheel does true offscreen rendering via OSMesa — no X server needed —
# but it links against the system OSMesa runtime, so libosmesa6 is REQUIRED (without it
# `import vtk`/render falls back to "no backend"). The stock PyPI `vtk` wheel is NOT used:
# it only ships vtkXOpenGLRenderWindow and cannot render on a headless host.
# libgl1: pulled in by the Mesa/OSMesa stack. libglib2.0-0 + libfreetype6: VTK / Pillow deps.
# All CPU-only — no GPU drivers installed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libosmesa6 \
        libgl1 \
        libglib2.0-0 \
        libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- runtime: copy application source ----
FROM deps AS runtime
# Copy backend source into /app so imports resolve as `from app.xxx import ...`
COPY backend/app/ ./app/
COPY backend/worker.py ./
COPY backend/alembic.ini ./
COPY backend/alembic/ ./alembic/
COPY backend/docker-entrypoint.sh ./
RUN chmod +x ./docker-entrypoint.sh

# Runtime-user env: set HOME and XDG_CACHE_HOME to /tmp so that libraries
# writing to $HOME (e.g. fontconfig, matplotlib) don't fail when the container
# runs as an arbitrary UID that has no passwd entry.  PUID/PGID are applied at
# container start via compose `user:` — no hardcoded USER here.
ENV HOME=/tmp \
    XDG_CACHE_HOME=/tmp

# Data directory will be mounted at runtime (./data:/data or named volume).
# 0777 so any UID (set via compose user: PUID:PGID) can write the named volume
# on first mount — Docker copies this mode when initialising a new named volume.
RUN mkdir -p /data && chmod 0777 /data

# The entrypoint applies DB migrations when RUN_MIGRATIONS=true (set on the
# backend service), then execs the service command — so migrations are bundled
# into startup with no separate one-shot container.
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default: run the FastAPI API server.
# The `worker` compose service overrides this to: python worker.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
