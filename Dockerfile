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
        libxrender1 \
        libxi6 \
    && rm -rf /var/lib/apt/lists/*
# libxrender1 + libxi6: pyrender imports pyglet at module load (and the vtk
# wheel links libXrender), so without these X11 client libs `import pyrender`
# and `import vtk` both fail with "libXrender.so.1: cannot open shared object
# file" — leaving NO working render backend even though libGL/EGL/OSMesa exist.

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# pyrender hard-pins PyOpenGL==3.1.0, which lacks OSMesaCreateContextAttribs and
# is too old for the EGL/OSMesa offscreen paths render_mesh.py needs. Override to
# a newer PyOpenGL after the pinned install (3.1.0 is overly strict; pyrender
# works fine with 3.1.7+). Without this, get_backend() returns "none".
RUN pip install --no-cache-dir "PyOpenGL>=3.1.7"

# ---- runtime: copy application source ----
FROM deps AS runtime
# Copy backend source into /app so imports resolve as `from app.xxx import ...`
COPY backend/app/ ./app/
COPY backend/worker.py ./
COPY backend/alembic.ini ./
COPY backend/alembic/ ./alembic/
COPY backend/docker-entrypoint.sh ./
RUN chmod +x ./docker-entrypoint.sh

# Data directory will be mounted at runtime (./data:/data in compose)
RUN mkdir -p /data

# The entrypoint applies DB migrations when RUN_MIGRATIONS=true (set on the
# backend service), then execs the service command — so migrations are bundled
# into startup with no separate one-shot container.
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default: run the FastAPI API server.
# The `worker` compose service overrides this to: python worker.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
