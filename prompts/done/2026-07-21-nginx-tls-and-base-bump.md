---
name: 2026-07-21-nginx-tls-and-base-bump
status: done          # pending | in-progress | done | failed
created: 2026-07-21
model: sonnet            # coding task
completed: 2026-07-21
result: >
  Implemented TLS_MODE=off|selfsigned|provided at nginx via a
  /docker-entrypoint.d/ script + a shared partfolder-common.conf include
  (:80 and runtime-generated :443 both include it), bumped nginx base image
  1.27-alpine -> 1.30-alpine in nginx/Dockerfile (closes #40) and, as a
  trivially-free bonus, docker-compose.dev.yml's stock nginx image. Verified
  by building the image and driving all four scenarios (off / selfsigned incl.
  cert-persists-across-restart / provided with a mounted cert / provided with
  the cert absent -> non-zero exit) plus both `docker compose config --quiet`
  runs. Docs (docs/tls.md, features-overview.md, architecture.md, README.md),
  .env.example, and CHANGELOG.md updated in the same change. Not committed —
  spawned agent per project convention; orchestrator commits + pushes to dev.
---

# Task: Optional TLS/HTTPS at nginx (self-signed + bring-your-own cert) + base-image security bump

Add first-class, opt-in TLS termination to the PartFolder nginx image so a **standalone
self-hoster** (no upstream Traefik/Caddy/NPM) can serve HTTPS directly — with either an
auto-generated self-signed cert or their own real ("official") cert. Bundle the nginx
**base-image security bump** (issue #40) into the same change since both touch the nginx image.

**Closes #40** (base-image bump). Implements the initial TLS support; full Let's Encrypt/ACME
automation is explicitly OUT OF SCOPE and tracked separately in **#41** — do not build ACME here.

## Owner decisions already made (do not re-litigate)

- **Two cert modes now:** `selfsigned` (auto-generated, the "user-generated / non-official" cert)
  and `provided` (user mounts their own real cert — "official cert support", BYO-mount style).
  Full auto Let's Encrypt is deferred to #41.
- **Base image:** bump `nginx:1.27-alpine` → **`nginx:1.30-alpine`** (stable branch; nginx.org's
  own recommendation for 1.27.x users re CVE-2026-42533 et al.; floating minor keeps the current
  pinning style and auto-picks ≥1.30.4). If you discover a concrete reason 1.30 won't work, STOP
  and report rather than silently choosing 1.31.
- **Default is unchanged behavior:** `TLS_MODE=off` (port 80 only) must be the default so existing
  deployments — including the owner's own Traefik-fronted prod — are byte-for-byte unaffected.

## Before you start

- **Read** `nginx/Dockerfile`, `nginx/nginx.conf`, `nginx/nginx.dev.conf`, the `nginx:` service in
  `docker-compose.yml`, and the `COOKIE_SECURE` block in `.env.example` (~line 238). Read the two
  GitHub issues: `gh issue view 40` and `gh issue view 41`.
- **Read** `docs/architecture.md` (nginx/CI rows) and `CLAUDE.md` (verify discipline). Record
  non-obvious decisions in `docs/decisions.md` (newest at top).
- **Working tree check:** you are running in an isolated git worktree — the tree should be clean.
  Run `git status --porcelain`; surface anything unexpected before editing.
- **No DB migration** (nginx/compose/docs only). Do not create one.

## Design to implement

### 1. `TLS_MODE` env — three values

| `TLS_MODE` | Behavior |
|---|---|
| `off` (default) | Today's config: one `server { listen 80; ... }`. No 443. Exactly current behavior. |
| `selfsigned` | On start, if no cert exists at the cert dir, generate a self-signed cert (openssl). Add a `listen 443 ssl` server using it. HTTPS works immediately with a browser trust warning. |
| `provided` | Expect `fullchain.pem` + `privkey.pem` mounted into the cert dir. Add a `listen 443 ssl` server using them. If either file is missing/unreadable, fail loudly with a clear log message (non-zero exit so the container doesn't silently serve plain HTTP). |

Additional env (document all in `.env.example`):
- `APP_HTTPS_PORT` (default `8443`) — host port mapped to container `443` (opt-in in compose).
- `TLS_REDIRECT` (default `false`) — when TLS is on and this is `true`, the `:80` server returns
  `301` → `https://$host:$server_port` … keep it simple and correct; if the redirect port math is
  fragile behind a mapped host port, redirect to `https://$host$request_uri` and note the caveat.
- Cert dir: default `/etc/nginx/certs` (both modes read/write here).

### 2. Avoid location duplication — factor shared config into an include

The `:80` and generated `:443` servers must serve identical locations/headers/limits. Refactor
`nginx/nginx.conf`: move everything **inside** the current `server { ... }` except `listen` /
`server_name` into an include file (e.g. `nginx/partfolder-common.conf` baked to
`/etc/nginx/partfolder-common.conf`). Both server blocks `include` it. This keeps the security
headers / CSP / `client_max_body_size 1024m` / all `location` blocks defined exactly once. Do not
change any header/CSP/location semantics — this is a pure extraction.

### 3. Runtime assembly via a `/docker-entrypoint.d/` script

Stock `nginx:alpine` runs `/docker-entrypoint.d/*.sh` before starting nginx. Add e.g.
`nginx/40-partfolder-tls.sh`, `COPY`d into `/docker-entrypoint.d/` and `chmod +x`. It must:
- Read `TLS_MODE` (default `off`).
- `off`: ensure no stray `tls.conf` is present; leave the baked `:80` config as-is.
- `selfsigned`: if `$CERT_DIR/privkey.pem`/`fullchain.pem` absent, generate a self-signed pair with
  openssl (e.g. `openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=${TLS_CN:-localhost}"`).
  Then write `/etc/nginx/conf.d/tls.conf` with a `listen 443 ssl;` server that `include`s the common
  file and points `ssl_certificate`/`ssl_certificate_key` at the cert dir. Persist certs to the cert
  dir (a volume — see compose) so they survive restarts.
- `provided`: verify both files exist and are non-empty; write the same `tls.conf`; on missing files
  log a clear error and `exit 1`.
- Add sane TLS hardening to the 443 server: `ssl_protocols TLSv1.2 TLSv1.3;` and a reasonable
  cipher/`ssl_session_cache` set. Keep it standard; don't over-engineer.
- Be idempotent (safe to re-run on container restart) and never leak the private key to logs.

Add `RUN apk add --no-cache openssl` to the Dockerfile (alpine nginx has no openssl by default).

### 4. Keep the build-time `nginx -t` validation working

The Dockerfile currently patches `backend:` → `127.0.0.1` and runs `nginx -t` on the baked `:80`
config. Preserve that. The runtime `tls.conf` is generated at container start (not baked), so build
-time `-t` only covers the `:80`/common config — that's fine. Ensure the common-include refactor
still passes the build-time `nginx -t`.

### 5. `docker-compose.yml` (prod) — opt-in, non-breaking

Under the `nginx` service, add (mostly commented, defaulting to today's behavior):
- `environment:` `TLS_MODE=${TLS_MODE:-off}`, `TLS_REDIRECT=${TLS_REDIRECT:-false}`.
- A commented `- "${APP_HTTPS_PORT:-8443}:443"` port line.
- A commented cert volume/mount example for both modes (a named `nginx_certs` volume for
  `selfsigned`; a bind-mount of the user's `fullchain.pem`/`privkey.pem` for `provided`).
- A short comment block explaining the three modes and the `COOKIE_SECURE=true` requirement when
  TLS is on. Do NOT change the default (`off`) path.

Leave `docker-compose.dev.yml` on plain HTTP (dev doesn't need TLS) unless trivially free; if you
touch it, keep dev working.

### 6. `.env.example`

Document `TLS_MODE`, `APP_HTTPS_PORT`, `TLS_REDIRECT`, the cert paths/volume, and a pointer that
`COOKIE_SECURE` MUST be `true` whenever TLS is on (self-signed included).

### 7. Docs + changelog

- `docs/` — add a concise TLS/HTTPS section (either in `docs/features-overview.md` or a new
  `docs/tls.md`, matching existing doc style): the three modes, how to supply a real cert, the
  self-signed browser-warning caveat, and the "put a real reverse proxy in front for auto Let's
  Encrypt (see #41)" note. Add a one-line README mention.
- `docs/architecture.md` — update the nginx row to mention the TLS entrypoint script + common include.
- `CHANGELOG.md [Unreleased]` — an `### Added` entry for optional HTTPS/TLS, and a `### Security`
  entry for the nginx base-image bump (mention #40). Same commit as the code.
- `⚠️ nginx config changed` — the release process greps `nginx/nginx.conf` diffs; since this changes
  it, that callout will fire at release time. That's expected; just make sure the config change is
  clean.

## Verify — build the image and DRIVE all three modes (this is the real gate)

`make verify` won't exercise nginx (no backend/frontend code changed). You MUST prove the image
works by building and running it:

1. `docker build -f nginx/Dockerfile -t pf3d-nginx-test .` — must succeed (incl. build-time `nginx -t`).
2. **`off`:** run the container with `TLS_MODE=off`; `curl -sf http://localhost:PORT/` returns the SPA
   (or the expected response without the frontend volume — a 200/404 from nginx, not a connection
   refuse). Confirm no `:443` listener.
3. **`selfsigned`:** run with `TLS_MODE=selfsigned`, cert volume empty; confirm the entrypoint
   generates a cert, `:443` serves TLS (`curl -k https://localhost:HTTPSPORT/` succeeds), and the
   cert persists on restart (re-run, no regeneration).
4. **`provided`:** generate a throwaway cert/key on the host, mount them, run with `TLS_MODE=provided`;
   confirm `:443` serves them. Then run `provided` with the files ABSENT and confirm the container
   exits non-zero with a clear error (does NOT silently fall back to plain HTTP).
5. Run `docker compose config --quiet` and `docker compose -f docker-compose.dev.yml config --quiet`
   — both must pass with the new env/volume/port additions.
6. Capture the exact commands + observed output for each mode in your report.

Clean up test containers/images afterward.

## Conventions to honor

- Match existing file/comment style. Shell script: `set -e`, POSIX `sh` (alpine has no bash), quote
  variables, no secrets in logs.
- Commit prefix `feat:` (the security bump rides along; mention it + `closes #40` in the body). No
  `Co-authored-by:` trailer. Changelog + docs in the SAME commit as the code.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record decisions in `docs/decisions.md` (TLS_MODE design, common-include refactor, base-image
   target, ACME deferral to #41).
4. **You are a spawned agent in a worktree: do NOT commit, do NOT push.** Prepare the tree, then
   report back to the orchestrator: the file list, a one-line `feat:` commit message (with
   `closes #40`), and the full verify evidence (build + all four mode smoke-tests + compose config).
   The orchestrator handles commit + push to `dev`.
