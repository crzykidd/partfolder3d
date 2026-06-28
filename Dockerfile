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

# ---- deps: system libraries + Python packages (cached layer) ----
FROM base AS deps

# GL/rendering libraries for headless mesh thumbnail generation (Phase 4).
# Priority order tried by render_mesh.py:
#   1. pyrender + EGL   (libgl1, libegl1, libgbm1)
#   2. pyrender + OSMesa (libosmesa6 — Mesa 22+ has OSMesaCreateContextAttribs)
#   3. VTK offscreen    (Mesa software rasterizer built into the VTK wheel; no extra libs needed)
# libglib2.0-0 and libfreetype6 are transitive deps of Mesa / Pillow.
# All are CPU-only — no GPU drivers installed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libegl1 \
        libgbm1 \
        libosmesa6 \
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

# Data directory will be mounted at runtime (./data:/data in compose)
RUN mkdir -p /data

# Default: run the FastAPI API server.
# The `worker` compose service overrides this to: python worker.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
