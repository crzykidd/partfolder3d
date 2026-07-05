"""FlareSolverr scraper client — pluggable fallback scraper backend (issue #23).

FlareSolverr is a free, self-hosted proxy that bypasses Cloudflare and similar
bot-protection challenges by running a headless browser.

Design mirrors agentql_client.py:
  - Sync httpx.Client — runs in asyncio.run_in_executor by the worker.
  - Always returns a ScrapeResult, never raises.
  - Errors → blocked=True with a clear note prefixed "FlareSolverr:".
  - Injectable seam for tests: monkeypatch _flaresolverr_caller to a mock callable.

SSRF posture:
  - The *target* URL (the page to scrape) is validated via assert_safe_url so
    FlareSolverr cannot be used as an SSRF proxy to reach internal hosts.
  - The *base_url* (the internal Docker host running FlareSolverr, e.g.
    http://flaresolverr:8191) is intentionally NOT guarded — it's an admin-
    configured internal service endpoint, not user-supplied.

FlareSolverr API shape (POST /v1):
  Request:  {"cmd": "request.get", "url": <target>, "maxTimeout": <ms>}
  Response: {"status": "ok"|"error", "message": ...,
             "solution": {"response": <html>, "status": <http_code>, "url": <final_url>}}

The root endpoint GET / returns {"msg": "FlareSolverr is ready!", "version": ...}
and is used for the test-connection health probe.

Docs: https://github.com/FlareSolverr/FlareSolverr
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from .scraper import ScrapeResult, extract_metadata_from_html
from .ssrf_guard import SSRFBlockedError, assert_safe_url, sanitize_for_log

log = logging.getLogger(__name__)

# Extra seconds added to the httpx timeout beyond FlareSolverr's maxTimeout.
# FlareSolverr blocks for up to maxTimeout waiting for the challenge solve, so
# our HTTP client must wait at least that long, plus a buffer for network RTT.
_TIMEOUT_PADDING_S: float = 15.0

# ---------------------------------------------------------------------------
# Injectable seam for tests (monkeypatch _flaresolverr_caller to a mock)
# ---------------------------------------------------------------------------

# None → use real httpx.  Set to callable(url: str, base_url: str) -> ScrapeResult.
_flaresolverr_caller: object | None = None


def _get_caller() -> object | None:
    """Return the injected caller (None = use real httpx)."""
    return _flaresolverr_caller


# ---------------------------------------------------------------------------
# Health probe (used by test-connection admin endpoint)
# ---------------------------------------------------------------------------


def flaresolverr_health(base_url: str, *, timeout_s: float = 10.0) -> dict:  # type: ignore[type-arg]
    """GET <base_url>/ and return the parsed JSON response.

    FlareSolverr's root handler returns:
      {"msg": "FlareSolverr is ready!", "version": "...", "userAgent": "..."}

    Raises on any HTTP or network error — callers catch and surface the message.
    """
    url = base_url.rstrip("/") + "/"
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Main client function
# ---------------------------------------------------------------------------


def flaresolverr_scrape(
    url: str,
    base_url: str,
    *,
    timeout_s: float = 60.0,
    max_images: int = 20,
) -> ScrapeResult:
    """Scrape a URL via a local FlareSolverr instance.

    Posts a ``request.get`` command to FlareSolverr's /v1 endpoint, reads the
    resolved HTML from ``solution.response``, and extracts metadata using the
    shared ``extract_metadata_from_html`` helper (same pipeline as the static
    scraper).

    Returns a ScrapeResult; never raises.  All errors produce ``blocked=True``
    with a note prefixed ``FlareSolverr:``.

    Args:
        url:        Target page URL (SSRF-guarded).
        base_url:   FlareSolverr instance URL (e.g. ``http://flaresolverr:8191``).
                    NOT SSRF-guarded — it's an admin-configured internal host.
        timeout_s:  Solve timeout forwarded to FlareSolverr as ``maxTimeout`` (ms).
                    The httpx client timeout is ``timeout_s + _TIMEOUT_PADDING_S``.
        max_images: Max image URLs to extract (passed to extract_metadata_from_html).
    """
    caller = _get_caller()
    if caller is not None:
        return caller(url, base_url)  # type: ignore[operator]

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    _su = sanitize_for_log(url)
    result = ScrapeResult(url=url, domain=domain)

    # SSRF guard on the *target* URL (not on base_url — that's an internal service).
    try:
        assert_safe_url(url)
    except SSRFBlockedError as exc:
        result.blocked = True
        result.note = f"FlareSolverr: SSRF guard blocked target URL — {exc}"
        log.warning("flaresolverr_scrape: SSRF blocked target %s: %s", _su, exc)
        return result

    max_timeout_ms = int(timeout_s * 1000)
    httpx_timeout = timeout_s + _TIMEOUT_PADDING_S

    body = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": max_timeout_ms,
    }

    try:
        with httpx.Client(timeout=httpx_timeout) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/v1",
                json=body,
                headers={"Content-Type": "application/json"},
            )

        if resp.status_code != 200:
            result.blocked = True
            result.note = f"FlareSolverr: HTTP {resp.status_code} from solver"
            log.warning(
                "flaresolverr_scrape: solver returned HTTP %s for %s",
                resp.status_code, _su,
            )
            return result

        data = resp.json()
        status = data.get("status", "")

        if status != "ok":
            msg = data.get("message", "unknown error")
            result.blocked = True
            result.note = f"FlareSolverr: solver error — {msg}"
            log.warning("flaresolverr_scrape: solver error for %s: %s", _su, msg)
            return result

        solution = data.get("solution") or {}
        sol_status = solution.get("status", 200)
        html = solution.get("response") or ""
        final_url = solution.get("url") or url

        # Non-2xx upstream status → still blocked
        if not (200 <= int(sol_status) < 300):
            result.blocked = True
            result.note = f"FlareSolverr: upstream returned HTTP {sol_status}"
            log.warning(
                "flaresolverr_scrape: upstream HTTP %s for %s", sol_status, _su
            )
            return result

        if not html:
            result.blocked = True
            result.note = (
                "FlareSolverr: empty response — page may still be protected."
            )
            log.warning("flaresolverr_scrape: empty HTML for %s", _su)
            return result

        # Parse the resolved HTML using the shared extraction helper.
        sr = extract_metadata_from_html(html, final_url, domain, max_images)
        sr.url = url  # preserve the original (pre-redirect) URL

        if not sr.title and not sr.description and not sr.image_urls:
            sr.blocked = True
            sr.note = (
                "FlareSolverr: returned HTML but no metadata extracted — "
                "page may still be protected."
            )
        else:
            sr.blocked = False

        log.info(
            "flaresolverr_scrape: %s → title=%r images=%d",
            _su, sr.title, len(sr.image_urls),
        )
        return sr

    except httpx.TimeoutException:
        result.blocked = True
        result.note = (
            f"FlareSolverr: request timed out after {httpx_timeout:.0f}s."
        )
        log.warning("flaresolverr_scrape: timeout for %s", _su)
        return result

    except Exception as exc:
        result.blocked = True
        result.note = f"FlareSolverr: unexpected error — {exc}"
        log.warning("flaresolverr_scrape: error for %s: %s", _su, exc)
        return result
