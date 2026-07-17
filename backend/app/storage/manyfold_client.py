"""Manyfold OAuth2 token-fetch client (Part 1 of 3 — see manyfold.py model).

Manyfold instances authenticate over OAuth2 using the ``client_credentials``
grant only. This module fetches a bearer access token for a registered
instance so the admin router's "test connection" can verify the credentials
work.

Part 2 will extend this file with model-metadata fetch + file download; keep
it small here.

Design mirrors flaresolverr_client.py / agentql_client.py:
  - Sync httpx.Client — callers run it in a thread/executor from async code.
  - Raises a typed ``ManyfoldError`` subclass on failure (this client is a
    single request/response call, not a best-effort scrape — callers want a
    clear reason to show the admin, not a silently-degraded result).
  - Injectable seam for tests: monkeypatch ``_manyfold_token_caller`` to a
    mock ``callable(token_url, form, timeout_s) -> (status_code, json_body)``.

SSRF posture:
  - ``base_url`` is admin-trusted config (an instance the admin explicitly
    registered via the admin API), NOT user-supplied per-request input — so
    it is intentionally NOT SSRF-guarded here, mirroring how FlareSolverr's
    configured ``base_url`` is exempt (see flaresolverr_client.py). Part 2
    handles the SSRF surface for the file-download path (which may follow
    redirects to object storage).

Manyfold OAuth token endpoint (authoritative, from the real source):
  POST {base_url}/oauth/token
  Body (form): grant_type=client_credentials&client_id=…&client_secret=…&scope=public read
  Response: {"access_token", "token_type": "Bearer", "expires_in": 7200,
             "scope", "created_at"}
  Errors: 401 bad/missing credentials, 403 scope not granted.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_SCOPES = "public read"


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
