# ---- base: install deps ----
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# ---- build: compile the Vite app ----
FROM deps AS builder
COPY . .
RUN npm run build \
 && node -p "require('./package.json').version" > /app/VERSION

# ---- prod: export the dist/ for consumption by nginx ----
# When used in docker-compose, cmd copies dist to the shared named volume.
# Alpine-only: no node/npm/node_modules in the shipped image (it only `cp`s static
# files, so the toolchain was pure CVE surface). Version banner reads /app/VERSION.
FROM alpine:3.24 AS prod
WORKDIR /app
COPY --from=builder /app/dist /app/dist
COPY --from=builder /app/VERSION /app/VERSION
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
# 0777 on /dist so any UID (set via compose user: PUID:PGID) can write the
# named volume — Docker copies this mode when initialising a new named volume.
RUN mkdir -p /dist && chmod 0777 /dist
# Default CMD: publish built assets to the /dist volume with a version banner +
# loud errors (frontend/docker-entrypoint.sh), then exit 0. No more silent exits.
CMD ["sh", "/app/docker-entrypoint.sh"]

# ---- dev: run Vite dev server with hot reload ----
# docker-compose.dev.yml overrides the service to use this target.
# Source files are bind-mounted at runtime; node_modules stay in the image.
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
