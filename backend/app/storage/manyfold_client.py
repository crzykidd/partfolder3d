"""Manyfold OAuth2 + model/file API client (Part 2 of 3 — see manyfold.py model).

Manyfold instances authenticate over OAuth2 using the ``client_credentials``
grant only. Part 1 added ``fetch_token``/``get_access_token`` so the admin
router's "test connection" can verify stored credentials work. This module
(Part 2) extends the client with model-metadata fetch + file download so the
import worker (``worker/tasks/import_session.py``) can pull a model straight
from a Manyfold URL.

Design mirrors flaresolverr_client.py / agentql_client.py:
  - Sync httpx.Client — callers run it in a thread/executor from async code.
  - Raises a typed ``ManyfoldError`` subclass on failure (this client makes
    single request/response calls, not a best-effort scrape — callers want a
    clear reason to show the user, not a silently-degraded result).
  - Injectable seams for tests: monkeypatch ``_manyfold_token_caller`` (token
    fetch), ``_manyfold_json_caller`` (model/file/creator JSON GETs), and
    ``_manyfold_download_caller`` (binary file download) to mock callables —
    no real HTTP in tests.

SSRF posture:
  - ``base_url`` is admin-trusted config (an instance the admin explicitly
    registered via the admin API), NOT user-supplied per-request input — so
    the model/file/creator JSON GETs are intentionally NOT SSRF-guarded here,
    mirroring how FlareSolverr's configured ``base_url`` is exempt (see
    flaresolverr_client.py).
  - ``download_file`` IS SSRF-guarded on every hop (initial request AND each
    redirect) via ``assert_safe_url`` — a ``contentUrl`` may 302-redirect to
    an object-storage host outside the admin-trusted instance, so that hop is
    treated as untrusted the same way ``guarded_fetch`` treats scrape
    redirects. See docs/decisions.md for the redirect-Authorization posture
    (the Bearer token is dropped once a redirect crosses to a different host).

Manyfold OAuth token endpoint (authoritative, from the real source):
  POST {base_url}/oauth/token
  Body (form): grant_type=client_credentials&client_id=…&client_secret=…&scope=public read
  Response: {"access_token", "token_type": "Bearer", "expires_in": 7200,
             "scope", "created_at"}
  Errors: 401 bad/missing credentials, 403 scope not granted.

Manyfold model/file API (authoritative, from the real source):
  GET {base_url}/models/{model_id}
    Headers: Authorization: Bearer <tok>, Accept: application/vnd.manyfold.v0+json
    Returns JSON-LD (schema.org): name, caption, description, keywords (tags),
    spdx:license, sensitive, creator (ref only), links, preview_file (ref),
    hasPart (array of ALL files, refs only — no download URL).
  GET {file "@id"}  (same headers)
    Returns {filename, encodingFormat, contentUrl, contentSize, previewable, ...}.
  GET {contentUrl}  (Authorization only, NO Accept override)
    Streams the binary; may 302 to an object-storage host.
  GET {creator "@id"}  (same headers as model fetch)
    Returns {name, slug, caption, description, links}.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from .ssrf_guard import assert_safe_url, sanitize_for_log

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_SCOPES = "public read"
MANYFOLD_ACCEPT = "application/vnd.manyfold.v0+json"
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class ManyfoldError(Exception):
    """Base error for Manyfold OAuth/API failures."""


class ManyfoldAuthError(ManyfoldError):
    """401 — invalid or missing OAuth client credentials."""


class ManyfoldScopeError(ManyfoldError):
    """403 — credentials valid but the requested scope was not granted."""


class ManyfoldConnectionError(ManyfoldError):
    """Network/timeout failure, or an unexpected response shape."""


class ManyfoldNotFoundError(ManyfoldError):
    """404 — the model or file does not exist (or isn't visible to this token)."""


# ---------------------------------------------------------------------------
# Model/file data structures (Part 2)
# ---------------------------------------------------------------------------


@dataclass
class ManyfoldFile:
    """One file entry from a model's ``hasPart`` array, with detail resolved."""

    id: str  # the file's "@id" URL — also used as the download-detail URL
    name: str
    filename: str
    encoding_format: str
    content_url: str | None
    content_size: int | None
    is_image: bool


@dataclass
class ManyfoldModel:
    """Parsed ``GET /models/{id}`` response."""

    title: str | None = None
    caption: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    license_id: str | None = None
    creator_name: str | None = None
    creator_profile_url: str | None = None
    links: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    sensitive: bool = False
    preview_file_id: str | None = None
    files: list[ManyfoldFile] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Injectable seam for tests (monkeypatch _manyfold_token_caller to a mock)
# ---------------------------------------------------------------------------

# None → use real httpx. Set to callable(token_url: str, form: dict,
# timeout_s: float) -> tuple[int, dict] in tests (status_code, json_body).
_manyfold_token_caller: object | None = None


def _get_caller() -> object | None:
    """Return the injected caller (None = use real httpx)."""
    return _manyfold_token_caller


# ---------------------------------------------------------------------------
# Token fetch
# ---------------------------------------------------------------------------


def fetch_token(
    base_url: str,
    client_id: str,
    client_secret: str,
    *,
    scopes: str = DEFAULT_SCOPES,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict:  # type: ignore[type-arg]
    """POST the OAuth token endpoint and return the parsed JSON response.

    Returns the full response body (``access_token``, ``token_type``,
    ``expires_in``, ``scope``, ``created_at``) so callers such as the
    test-connection endpoint can report the granted scope back to the admin.

    Raises:
        ManyfoldAuthError: HTTP 401 — bad/missing client credentials.
        ManyfoldScopeError: HTTP 403 — scope not granted.
        ManyfoldConnectionError: network/timeout error, or any other
            non-200 / malformed response.
    """
    token_url = base_url.rstrip("/") + "/oauth/token"
    form = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scopes,
    }

    caller = _get_caller()
    if caller is not None:
        status_code, body = caller(token_url, form, timeout_s)  # type: ignore[operator]
    else:
        try:
            with httpx.Client(timeout=timeout_s) as client:
                resp = client.post(token_url, data=form)
        except httpx.TimeoutException as exc:
            raise ManyfoldConnectionError(
                f"Timed out connecting to {base_url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ManyfoldConnectionError(f"Connection error: {exc}") from exc

        status_code = resp.status_code
        try:
            body = resp.json()
        except ValueError:
            body = {}

    if status_code == 401:
        raise ManyfoldAuthError("Invalid or missing client credentials.")
    if status_code == 403:
        raise ManyfoldScopeError("Requested scope was not granted.")
    if status_code != 200:
        raise ManyfoldConnectionError(
            f"Unexpected HTTP {status_code} from {base_url}."
        )
    if not isinstance(body, dict) or not body.get("access_token"):
        raise ManyfoldConnectionError("Token response missing access_token.")

    return body  # type: ignore[no-any-return]


def get_access_token(
    base_url: str,
    client_id: str,
    client_secret: str,
    *,
    scopes: str = DEFAULT_SCOPES,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> str:
    """Fetch a bearer access token via the OAuth2 client_credentials grant.

    Thin wrapper over ``fetch_token`` for callers that only need the token
    string (Part 2's download/model-fetch calls). See ``fetch_token`` for the
    errors this can raise.
    """
    body = fetch_token(
        base_url, client_id, client_secret, scopes=scopes, timeout_s=timeout_s
    )
    return str(body["access_token"])


# ---------------------------------------------------------------------------
# In-process token cache, keyed by ManyfoldInstance.id (Part 2)
# ---------------------------------------------------------------------------

# instance_id -> (token, monotonic expiry). A worker process lives for many
# imports, so caching avoids a token round-trip per model. Not persisted /
# shared across processes — a restart just refetches.
_token_cache: dict[int, tuple[str, float]] = {}

# Refresh this many seconds before the token's actual expires_in elapses, so a
# token that's about to expire mid-request isn't handed out.
_TOKEN_SAFETY_MARGIN_S = 60.0
_DEFAULT_TOKEN_TTL_S = 7200.0  # Manyfold's documented expires_in default


def get_cached_access_token(
    instance_id: int,
    base_url: str,
    client_id: str,
    client_secret: str,
    *,
    scopes: str = DEFAULT_SCOPES,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    force_refresh: bool = False,
) -> str:
    """Return a bearer token for *instance_id*, cached in-process until expiry.

    Reuses a cached token until ``expires_in`` seconds (minus a safety margin)
    have elapsed, then transparently refetches. Pass ``force_refresh=True``
    (e.g. after the API itself returns 401 despite a locally-unexpired cache
    entry — the token may have been revoked server-side) to bypass the cache
    once and store the freshly fetched token.
    """
    now = time.monotonic()
    if not force_refresh:
        cached = _token_cache.get(instance_id)
        if cached is not None and cached[1] > now:
            return cached[0]

    body = fetch_token(
        base_url, client_id, client_secret, scopes=scopes, timeout_s=timeout_s
    )
    token = str(body["access_token"])
    try:
        ttl = float(body.get("expires_in") or _DEFAULT_TOKEN_TTL_S)
    except (TypeError, ValueError):
        ttl = _DEFAULT_TOKEN_TTL_S
    _token_cache[instance_id] = (
        token,
        now + max(ttl - _TOKEN_SAFETY_MARGIN_S, 30.0),
    )
    return token


def _clear_token_cache() -> None:
    """Test-only: reset the in-process token cache between tests."""
    _token_cache.clear()


# ---------------------------------------------------------------------------
# Model ID parsing (Part 2)
# ---------------------------------------------------------------------------


def parse_model_id(url: str) -> str | None:
    """Extract the model slug from a Manyfold model URL.

    Matches ``.../models/{id}``, tolerating a trailing path segment, query
    string, or fragment. Returns ``None`` when the URL isn't a model page
    (e.g. a collection or profile URL).
    """
    path = urlparse(url).path
    parts = [p for p in path.split("/") if p]
    for i, part in enumerate(parts):
        if part == "models" and i + 1 < len(parts):
            candidate = parts[i + 1].strip()
            if candidate:
                return candidate
    return None


# ---------------------------------------------------------------------------
# Injectable seams for the JSON GET + binary download calls (Part 2)
# ---------------------------------------------------------------------------

# None → use real httpx. Test seam: callable(url: str, headers: dict,
# timeout_s: float) -> tuple[int, dict] (status_code, json_body). Used for the
# model/file-detail/creator GETs (all share the same Bearer + Manyfold-Accept
# request shape).
_manyfold_json_caller: object | None = None

# None → use real httpx. Test seam: callable(url: str, headers: dict,
# timeout_s: float) -> tuple[int, dict[str, str], bytes] (status_code,
# response_headers (lowercased keys), body). Used by download_file for both
# the initial request and each redirect hop.
_manyfold_download_caller: object | None = None


def _json_get(url: str, token: str, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
    """GET *url* with Bearer auth + the Manyfold JSON Accept header.

    Raises ManyfoldAuthError (401), ManyfoldNotFoundError (404), or
    ManyfoldConnectionError (any other non-200 / network failure / malformed
    body).
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": MANYFOLD_ACCEPT}

    caller = _manyfold_json_caller
    if caller is not None:
        status_code, body = caller(url, headers, timeout_s)  # type: ignore[operator]
    else:
        try:
            with httpx.Client(timeout=timeout_s) as client:
                resp = client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise ManyfoldConnectionError(
                f"Timed out fetching {sanitize_for_log(url)}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ManyfoldConnectionError(
                f"Connection error fetching {sanitize_for_log(url)}: {exc}"
            ) from exc
        status_code = resp.status_code
        try:
            body = resp.json()
        except ValueError:
            body = {}

    if status_code == 401:
        raise ManyfoldAuthError(f"Unauthorized fetching {sanitize_for_log(url)}.")
    if status_code == 404:
        raise ManyfoldNotFoundError(f"Not found: {sanitize_for_log(url)}")
    if status_code != 200:
        raise ManyfoldConnectionError(
            f"Unexpected HTTP {status_code} fetching {sanitize_for_log(url)}."
        )
    if not isinstance(body, dict):
        raise ManyfoldConnectionError(
            f"Malformed JSON response from {sanitize_for_log(url)}."
        )
    return body  # type: ignore[no-any-return]


def resolve_creator(
    base_url: str,
    creator_id: str,
    token: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict | None:  # type: ignore[type-arg]
    """Best-effort GET of a creator resource (``creator["@id"]`` from a model).

    Returns ``{"name": ..., "profile_url": ...}`` or ``None`` on any failure —
    creator resolution is a nice-to-have, never worth failing the whole import.
    """
    try:
        data = _json_get(creator_id, token, timeout_s=timeout_s)
    except Exception:
        log.debug(
            "resolve_creator: failed to resolve %s (best-effort, ignored)",
            sanitize_for_log(creator_id),
        )
        return None

    name = data.get("name")
    if not name or not str(name).strip():
        return None

    slug = data.get("slug")
    profile_url = (
        f"{base_url.rstrip('/')}/creators/{slug}" if slug else str(creator_id)
    )
    return {"name": str(name).strip(), "profile_url": profile_url}


def fetch_model(
    base_url: str,
    model_id: str,
    token: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ManyfoldModel:
    """GET a model's JSON-LD metadata and resolve every ``hasPart`` file detail.

    Each file entry in ``hasPart`` carries no download URL — a second GET per
    file (its ``@id``) is required to learn ``contentUrl``/``contentSize``. A
    single file-detail failure is logged and that file is skipped (best-effort:
    a model with one broken file entry shouldn't fail the whole import).

    Creator resolution (``creator["@id"]``) is best-effort via
    ``resolve_creator``; a failure there leaves ``creator_name``/
    ``creator_profile_url`` as ``None`` rather than failing the fetch.

    Raises ManyfoldAuthError/ManyfoldNotFoundError/ManyfoldConnectionError
    (propagated from the model GET itself — this call must succeed).
    """
    url = f"{base_url.rstrip('/')}/models/{model_id}"
    data = _json_get(url, token, timeout_s=timeout_s)

    title = data.get("name")
    caption = data.get("caption")
    description = data.get("description")

    keywords = data.get("keywords")
    tags: list[str] = []
    if isinstance(keywords, list):
        tags = [str(k).strip() for k in keywords if str(k).strip()]
    elif isinstance(keywords, str) and keywords.strip():
        tags = [keywords.strip()]

    license_id: str | None = None
    lic = data.get("spdx:license")
    if isinstance(lic, dict) and lic.get("licenseId"):
        license_id = str(lic["licenseId"])

    sensitive = bool(data.get("sensitive", False))

    creator_id: str | None = None
    creator_ref = data.get("creator")
    if isinstance(creator_ref, dict) and creator_ref.get("@id"):
        creator_id = str(creator_ref["@id"])

    links_raw = data.get("links")
    links: list[dict] = (  # type: ignore[type-arg]
        [link_entry for link_entry in links_raw if isinstance(link_entry, dict)]
        if isinstance(links_raw, list)
        else []
    )

    preview_ref = data.get("preview_file")
    preview_file_id: str | None = None
    if isinstance(preview_ref, dict) and preview_ref.get("@id"):
        preview_file_id = str(preview_ref["@id"])

    files: list[ManyfoldFile] = []
    has_part = data.get("hasPart")
    if isinstance(has_part, list):
        for part in has_part:
            if not isinstance(part, dict) or not part.get("@id"):
                continue
            file_id = str(part["@id"])
            part_name = str(part.get("name") or "")
            try:
                detail = _json_get(file_id, token, timeout_s=timeout_s)
            except ManyfoldError as exc:
                log.warning(
                    "fetch_model: file detail fetch failed for %s: %s",
                    sanitize_for_log(file_id), exc,
                )
                continue
            encoding_format = str(
                detail.get("encodingFormat") or part.get("encodingFormat") or ""
            )
            content_size = detail.get("contentSize")
            files.append(
                ManyfoldFile(
                    id=file_id,
                    name=part_name,
                    filename=str(detail.get("filename") or part_name or file_id),
                    encoding_format=encoding_format,
                    content_url=(
                        str(detail["contentUrl"]) if detail.get("contentUrl") else None
                    ),
                    content_size=(
                        int(content_size) if isinstance(content_size, int | float) else None
                    ),
                    is_image=encoding_format.lower().startswith("image/"),
                )
            )

    creator_name: str | None = None
    creator_profile_url: str | None = None
    if creator_id:
        resolved = resolve_creator(base_url, creator_id, token, timeout_s=timeout_s)
        if resolved:
            creator_name = resolved.get("name")
            creator_profile_url = resolved.get("profile_url")

    return ManyfoldModel(
        title=str(title).strip() if title else None,
        caption=str(caption).strip() if caption else None,
        description=str(description).strip() if description else None,
        tags=tags,
        license_id=license_id,
        creator_name=creator_name,
        creator_profile_url=creator_profile_url,
        links=links,
        sensitive=sensitive,
        preview_file_id=preview_file_id,
        files=files,
    )


def download_file(
    url: str,
    token: str,
    dest_path: Path,
    *,
    max_bytes: int,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_redirects: int = 5,
) -> int:
    """Download a Manyfold file (image or 3D asset) to *dest_path*.

    Follows redirects manually (never httpx's auto-follow) so every hop can be
    re-validated with ``assert_safe_url`` — a ``contentUrl`` may 302 to an
    object-storage host outside the admin-trusted instance, which is exactly
    the SSRF surface ``guarded_fetch`` closes for the scrape path. The Bearer
    token is sent on the initial request and on any redirect that stays on the
    same host; it is dropped the moment a redirect crosses to a different
    host, so it is never leaked to a third-party object-storage endpoint.

    Enforces *max_bytes*, aborting before the full body is buffered.

    Raises:
        SSRFBlockedError: a hop's target resolves to a private/internal host.
        ManyfoldConnectionError: network failure, non-200 final status, no
            Location header on a redirect, too many redirects, or the body
            exceeded max_bytes.

    Returns the number of bytes written.
    """
    original_host = urlparse(url).netloc
    current_url = url
    send_auth = True
    caller = _manyfold_download_caller

    for _hop in range(max_redirects + 1):
        # SSRF re-guard on every hop, including the first.
        assert_safe_url(current_url)

        headers: dict[str, str] = {}
        if send_auth:
            headers["Authorization"] = f"Bearer {token}"

        if caller is not None:
            status_code, resp_headers, body = caller(  # type: ignore[operator]
                current_url, headers, timeout_s
            )
        else:
            try:
                with httpx.Client(
                    timeout=timeout_s, follow_redirects=False
                ) as client, client.stream(
                    "GET", current_url, headers=headers
                ) as resp:
                    if resp.status_code in _REDIRECT_CODES:
                        resp.read()
                        status_code = resp.status_code
                        resp_headers = {
                            k.lower(): v for k, v in resp.headers.items()
                        }
                        body = b""
                    else:
                        chunks: list[bytes] = []
                        total = 0
                        for chunk in resp.iter_bytes():
                            total += len(chunk)
                            if total > max_bytes:
                                raise ManyfoldConnectionError(
                                    f"File exceeded {max_bytes} bytes: "
                                    f"{sanitize_for_log(current_url)}"
                                )
                            chunks.append(chunk)
                        status_code = resp.status_code
                        resp_headers = {
                            k.lower(): v for k, v in resp.headers.items()
                        }
                        body = b"".join(chunks)
            except httpx.TimeoutException as exc:
                raise ManyfoldConnectionError(
                    f"Timed out downloading {sanitize_for_log(current_url)}."
                ) from exc
            except httpx.HTTPError as exc:
                raise ManyfoldConnectionError(
                    f"Connection error downloading {sanitize_for_log(current_url)}: {exc}"
                ) from exc

        if status_code in _REDIRECT_CODES:
            location = resp_headers.get("location")
            if not location:
                raise ManyfoldConnectionError(
                    f"Redirect with no Location header: "
                    f"{sanitize_for_log(current_url)}"
                )
            next_url = urljoin(current_url, location)
            # Validate the hop target BEFORE following (belt-and-braces: the
            # top of the next loop iteration re-checks it too).
            assert_safe_url(next_url)
            send_auth = urlparse(next_url).netloc == original_host
            current_url = next_url
            continue

        if status_code != 200:
            raise ManyfoldConnectionError(
                f"Unexpected HTTP {status_code} downloading "
                f"{sanitize_for_log(current_url)}."
            )

        if len(body) > max_bytes:
            raise ManyfoldConnectionError(
                f"File exceeded {max_bytes} bytes: {sanitize_for_log(current_url)}"
            )

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(body)
        return len(body)

    raise ManyfoldConnectionError(
        f"Too many redirects (>{max_redirects}) downloading {sanitize_for_log(url)}"
    )
