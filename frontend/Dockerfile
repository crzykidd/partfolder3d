# ---- base: install deps ----
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# ---- build: compile the Vite app ----
FROM deps AS builder
COPY . .
RUN npm run build

# ---- prod: export the dist/ for consumption by nginx ----
# When used in docker-compose, cmd copies dist to the shared named volume.
FROM builder AS prod
# Default CMD: copy built assets to the /dist volume mount and exit cleanly.
CMD ["/bin/sh", "-c", "cp -rp /app/dist/. /dist/ && echo 'Frontend dist ready'"]

# ---- dev: run Vite dev server with hot reload ----
# docker-compose.dev.yml overrides the service to use this target.
# Source files are bind-mounted at runtime; node_modules stay in the image.
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
