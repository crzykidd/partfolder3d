FROM nginx:1.30-alpine

# nginx.org guidance for 1.27.x users (CVE-2026-42533 et al., fixed in
# 1.30.4+/1.31.3+): move to the 1.30 stable branch. Floating minor keeps the
# existing pinning style and auto-picks the latest >=1.30.4 patch. Issue #40.
#
# openssl is needed at runtime by nginx/40-partfolder-tls.sh to generate a
# self-signed cert when TLS_MODE=selfsigned — alpine's nginx image has no
# openssl by default.
RUN apk add --no-cache openssl

# Bake the production nginx config so the image works on a pull-only host
# (no ./nginx/nginx.conf bind-mount required at runtime). partfolder-common.conf
# holds the shared headers/CSP/locations, `include`d by BOTH the baked :80
# server and the runtime-generated :443 TLS server (see below) — one copy,
# never drifts. partfolder-redirect.conf is the (empty-by-default) runtime
# hook for TLS_REDIRECT.
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx/partfolder-common.conf /etc/nginx/partfolder-common.conf
COPY nginx/partfolder-redirect.conf /etc/nginx/partfolder-redirect.conf

# Optional TLS/HTTPS assembly (TLS_MODE=off|selfsigned|provided), run by the
# stock nginx image's /docker-entrypoint.d/ mechanism before nginx starts.
# See docs/tls.md.
COPY nginx/40-partfolder-tls.sh /docker-entrypoint.d/40-partfolder-tls.sh
RUN chmod +x /docker-entrypoint.d/40-partfolder-tls.sh

# Bake the logo/brand images at /usr/share/nginx/img/ — a path OUTSIDE the
# frontend_dist volume mount (/usr/share/nginx/html) so they are always present
# regardless of whether the volume has been populated yet.
# Served under /img/ via the location block in nginx.conf.
COPY docs/images/ /usr/share/nginx/img/

# Validate the baked config at build time — fail fast on any syntax error.
# The runtime-generated :443 tls.conf is NOT baked (it doesn't exist yet at
# build time), so this only covers the :80/common config — that's expected;
# see the "Verify" section of docs/tls.md for the runtime smoke-tests.
# /etc/hosts is read-only in BuildKit; the "backend" upstream only exists at
# runtime via Docker DNS. Temporarily patch the configs to use 127.0.0.1 for
# the -t test, then restore the originals. The final image always contains
# the original configs with the correct upstream reference. The "backend:"
# upstream now lives in partfolder-common.conf (post common-include
# refactor), not default.conf itself, so both are patched/restored.
RUN set -e; \
    cp /etc/nginx/conf.d/default.conf /tmp/nginx-default.bak; \
    cp /etc/nginx/partfolder-common.conf /tmp/partfolder-common.bak; \
    sed -i 's|http://backend:|http://127.0.0.1:|g' /etc/nginx/conf.d/default.conf /etc/nginx/partfolder-common.conf; \
    nginx -t; \
    cp /tmp/nginx-default.bak /etc/nginx/conf.d/default.conf; \
    cp /tmp/partfolder-common.bak /etc/nginx/partfolder-common.conf

# At runtime the frontend_dist named volume is mounted at /usr/share/nginx/html
# (populated by the frontend init-container). Nginx serves static assets from
# there; /img/ is served from the baked layer above.
