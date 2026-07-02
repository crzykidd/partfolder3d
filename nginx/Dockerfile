FROM nginx:1.27-alpine

# Bake the production nginx config so the image works on a pull-only host
# (no ./nginx/nginx.conf bind-mount required at runtime).
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

# Bake the logo/brand images at /usr/share/nginx/img/ — a path OUTSIDE the
# frontend_dist volume mount (/usr/share/nginx/html) so they are always present
# regardless of whether the volume has been populated yet.
# Served under /img/ via the location block in nginx.conf.
COPY docs/images/ /usr/share/nginx/img/

# Validate the baked config at build time — fail fast on any syntax error.
# /etc/hosts is read-only in BuildKit; the "backend" upstream only exists at
# runtime via Docker DNS. Temporarily patch the config to use 127.0.0.1 for the
# -t test, then restore the original. The final image always contains the
# original config with the correct upstream reference.
RUN set -e; \
    cp /etc/nginx/conf.d/default.conf /tmp/nginx-default.bak; \
    sed -i 's|http://backend:|http://127.0.0.1:|g' /etc/nginx/conf.d/default.conf; \
    nginx -t; \
    cp /tmp/nginx-default.bak /etc/nginx/conf.d/default.conf

# At runtime the frontend_dist named volume is mounted at /usr/share/nginx/html
# (populated by the frontend init-container). Nginx serves static assets from
# there; /img/ is served from the baked layer above.
