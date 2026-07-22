# PartFolder 3D — TLS / HTTPS at nginx

Operator guide for serving HTTPS directly from the bundled nginx image, for
**standalone self-hosters** who don't already run a reverse proxy
(Traefik/Caddy/nginx-proxy-manager) in front of PartFolder 3D.

> **Scope:** this covers `TLS_MODE=selfsigned` (auto-generated, non-official cert) and
> `TLS_MODE=provided` (your own real, "official" cert — bring-your-own-mount). **Fully
> automatic Let's Encrypt / ACME issuance is NOT implemented here** — that is tracked
> separately in issue #41. If you want a real, trusted, auto-renewing cert with zero
> manual cert management today, put a real reverse proxy (Traefik, Caddy,
> nginx-proxy-manager) in front and leave `TLS_MODE=off`.

---

## The three modes

Set `TLS_MODE` in `.env` (see `.env.example`):

| `TLS_MODE` | Behavior |
|---|---|
| `off` (default) | Plain `:80` only — today's behavior, unchanged. Existing deployments, including a Traefik-fronted setup, are byte-for-byte unaffected. |
| `selfsigned` | On container start, if no cert exists yet in the cert dir, nginx generates a self-signed cert with `openssl` and serves `:443` with it. HTTPS works immediately; browsers show a trust warning (expected — it isn't signed by a public CA). The generated cert persists across restarts if you mount the cert dir as a volume (see below). |
| `provided` | You mount your own real `fullchain.pem` + `privkey.pem` into the cert dir. If either file is missing or empty, the container **fails to start with a clear error** — it never silently falls back to plain HTTP when you asked for TLS. |

## Required companion settings

- `APP_HTTPS_PORT` (default `8443`) — the host port mapped to the container's `:443`.
  Uncomment the matching port line in the `nginx:` service in `docker-compose.yml`.
- `TLS_REDIRECT` (default `false`) — when TLS is on and this is `true`, the `:80`
  server 301-redirects every request to `https://$host$request_uri`. Left simple on
  purpose: redirecting to a fixed `https://$host:$server_port` gets the port math wrong
  once you're behind a mapped host port (`$server_port` inside the container is `80`,
  not your real external `APP_HTTPS_PORT`), so the redirect target omits the port and
  relies on the browser/client already knowing (or being told out-of-band) which HTTPS
  port to use. If your HTTPS port isn't the default `443`, you'll need to communicate
  that separately (e.g. a DNS/proxy layer in front, or just tell your users).
- `COOKIE_SECURE=true` — **required** whenever TLS is on (selfsigned included).
  Session cookies are marked `Secure` and won't be sent back over plain HTTP; leaving
  this `false` while serving HTTPS breaks login.

## Cert directory

Both `selfsigned` and `provided` read/write the same path inside the container:
`/etc/nginx/certs` (override with `CERT_DIR` if you really need to). It expects exactly
two files: `fullchain.pem` and `privkey.pem`.

### `selfsigned` — persisting the generated cert

Uncomment the `nginx_certs` named volume in `docker-compose.yml` (both the top-level
`volumes:` entry and the `nginx:` service's `- nginx_certs:/etc/nginx/certs` mount).
Without it, a fresh self-signed cert is generated on every container recreate — which
still works, just means a new "browser doesn't trust this yet" click each time and a
different cert fingerprint.

### `provided` — mounting your own cert

Bind-mount your real certificate files read-only, e.g.:

```yaml
volumes:
  - ./certs/fullchain.pem:/etc/nginx/certs/fullchain.pem:ro
  - ./certs/privkey.pem:/etc/nginx/certs/privkey.pem:ro
```

Renewal (e.g. from an external certbot run, or a cert issued by your registrar) is on
you — drop the renewed files at those paths and restart the `nginx` container to pick
them up.

## How it's implemented

- `nginx/nginx.conf` bakes only the plain `:80` server into the image.
- `nginx/partfolder-common.conf` holds every shared location/header/CSP/upload-limit
  directive, `include`d by **both** the baked `:80` server and the runtime-generated
  `:443` server — one copy, so the two listeners can never drift apart.
- At container start, `nginx/40-partfolder-tls.sh` (a `/docker-entrypoint.d/` script,
  the stock nginx image's hook mechanism) reads `TLS_MODE`, generates or verifies the
  cert as needed, and writes `/etc/nginx/conf.d/tls.conf` — a `listen 443 ssl;` server
  with `ssl_protocols TLSv1.2 TLSv1.3;` and a standard cipher/session-cache set — that
  also `include`s `partfolder-common.conf`. It's idempotent (safe on every restart) and
  never logs certificate/key contents.
- `TLS_MODE=provided` with missing/empty cert files makes the script `exit 1`, which
  (via the stock entrypoint's `set -e`) stops the container from starting nginx at all.

## Not in scope (see issue #41)

Fully automatic Let's Encrypt / ACME issuance and renewal — obtaining a real, publicly
trusted cert with zero manual steps — is a separate, larger effort (needs reachable
ports 80/443, a real domain, ACME challenge handling, and a renewal loop). If you need
that today, run a real reverse proxy in front of PartFolder 3D instead.
