"""AgentQL REST scraper client (Phase 18).

Calls the AgentQL REST API (https://api.agentql.com/v1/query-data) to fetch
metadata from Cloudflare-gated pages that the static scraper cannot reach.

This is a FALLBACK: it is only invoked when the static scraper is blocked.
Never used for sites that scrape fine (Printables, Thingiverse, etc.).

Design:
  - Sync httpx.Client — runs in asyncio.run_in_executor by the worker.
  - Always returns a ScrapeResult, never raises.
  - Errors → blocked=True with a clear note.
  - Injectable seam for tests: monkeypatch _agentql_caller to a mock function;
    the real HTTP call is never made in tests.

Proven working request params (tested live vs MakerWorld, HTTP 200, ~21s):
  POST https://api.agentql.com/v1/query-data
  Header: X-API-Key: <key>
  Body:
    {
      "query": "{ title description images[] { image_url } }",
      "url": "<target_url>",
      "params": {
        "mode": "standard",
        "browser_profile": "stealth",
        "wait_for": 6,
        "proxy": { "type": "tetra", "country_code": "US" }
      }
    }

Response shape:
  {
    "data": {
      "title": str,
      "description": str,
      "images": [{"image_url": str}, ...]
    },
    "metadata": { "request_id": ... }
  }

Stealth profile + Tetra proxy defeats Cloudflare — use as defaults.
Proxy can be disabled via proxy_enabled=False (cheaper, but may be blocked).
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from .scraper import ScrapeResult

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENTQL_API_URL = "https://api.agentql.com/v1/query-data"
AGENTQL_TIMEOUT = 120  # seconds; browser + proxy + challenge can take ~20s

# AQL query for metadata extraction
_AQL_QUERY = "{ title description images[] { image_url } }"

# ---------------------------------------------------------------------------
# Injectable seam for tests (monkeypatch _agentql_caller to a mock callable)
# ---------------------------------------------------------------------------

# None → use the real httpx implementation.
# Set to a callable(url: str, api_key: str) -> ScrapeResult in tests.
_agentql_caller: object | None = None


def _get_caller() -> object | None:
    """Return the injected caller (None = use real httpx)."""
    return _agentql_caller


# ---------------------------------------------------------------------------
# Main client function
# ---------------------------------------------------------------------------


def agentql_scrape(
    url: str,
    api_key: str,
    *,
    proxy_enabled: bool = True,
    proxy_country: str = "US",
    wait_for: int = 6,
) -> ScrapeResult:
    """Scrape metadata from a Cloudflare-gated URL via the AgentQL REST API.

    Returns a ScrapeResult; never raises.  Errors set result.blocked=True and
    result.note with a human-readable message.

    Args:
        url: The page URL to scrape.
        api_key: Plaintext AgentQL API key (decrypted by the caller).
        proxy_enabled: Use the Tetra proxy (default True; defeats Cloudflare).
        proxy_country: ISO country code for Tetra proxy (default "US").
        wait_for: Seconds for the browser to wait before extraction (default 6).
    """
    caller = _get_caller()
    if caller is not None:
        # Injected mock — call it directly
        return caller(url, api_key)  # type: ignore[operator]

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    result = ScrapeResult(url=url, domain=domain)

    # Build request body
    params: dict = {
        "mode": "standard",
        "browser_profile": "stealth",
        "wait_for": wait_for,
    }
    if proxy_enabled:
        params["proxy"] = {"type": "tetra", "country_code": proxy_country}

    body = {
        "query": _AQL_QUERY,
        "url": url,
        "params": params,
    }

    try:
        with httpx.Client(timeout=AGENTQL_TIMEOUT) as client:
            resp = client.post(
                AGENTQL_API_URL,
                json=body,
                headers={
                    "X-API-Key": api_key,
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code == 401:
            result.blocked = True
            result.note = "AgentQL: authentication failed — check your API key."
            log.warning("agentql_scrape: 401 Unauthorized for %s", url)
            return result

        if resp.status_code == 402:
            result.blocked = True
            result.note = "AgentQL: payment required or quota exceeded on their side."
            log.warning("agentql_scrape: 402 for %s", url)
            return result

        if resp.status_code != 200:
            result.blocked = True
            result.note = f"AgentQL: HTTP {resp.status_code}"
            log.warning("agentql_scrape: HTTP %s for %s", resp.status_code, url)
            return result

        data = resp.json()
        inner = data.get("data") or {}

        result.title = inner.get("title") or None
        result.description = inner.get("description") or None

        images_raw = inner.get("images") or []
        result.image_urls = [
            img["image_url"]
            for img in images_raw
            if isinstance(img, dict) and img.get("image_url")
        ]

        # Derive source_site from domain
        result.source_site = domain

        if not result.title and not result.description and not result.image_urls:
            result.blocked = True
            result.note = "AgentQL returned an empty response — the page may still be protected."
        else:
            result.blocked = False

        log.info(
            "agentql_scrape: %s → title=%r images=%d",
            url, result.title, len(result.image_urls),
        )
        return result

    except httpx.TimeoutException:
        result.blocked = True
        result.note = f"AgentQL: request timed out after {AGENTQL_TIMEOUT}s."
        log.warning("agentql_scrape: timeout for %s", url)
        return result

    except Exception as exc:
        result.blocked = True
        result.note = f"AgentQL: unexpected error — {exc}"
        log.warning("agentql_scrape: error for %s: %s", url, exc)
        return result
