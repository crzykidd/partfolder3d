"""URL scraper for the Phase 5 import wizard.

Fetches public metadata, images, tags, creator, and license from a source URL
for pre-filling the import wizard.

Design:
  - Uses httpx (already in requirements.txt) for async HTTP.
  - Uses selectolax for fast HTML parsing.
  - Extracts Open Graph tags first (og:title, og:description, og:image, og:site_name)
    then falls back to standard HTML meta/title tags.
  - Respects robots.txt at the per-domain level:
      * Checks /robots.txt for the domain.
      * Respects "User-agent: * Disallow: /" and "Disallow: <path>" rules.
      * Caches the robots check in-process for the session lifetime.
  - Files: never auto-downloads gated files.  Files require user supply or token.
  - Scrape failures degrade to the manual path (returns empty ScrapeResult).
  - Site capabilities are probed on first hit and stored via the caller.

All network I/O is sync (httpx.Client) so it can run inside an arq worker task
without needing a running event loop for the HTTP calls themselves.  Callers that
are already async should use asyncio.to_thread() or similar.

Decisions recorded in docs/decisions.md.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .ssrf_guard import (
    GuardedFetchError,
    SSRFBlockedError,
    assert_safe_url,
    guarded_fetch,
    sanitize_for_log,
)

log = logging.getLogger(__name__)

# Robots files are tiny; cap the fetch hard so a hostile host can't stream MBs.
_ROBOTS_MAX_BYTES = 512 * 1024
# Default HTML body cap (bytes) if a caller doesn't override it.  The worker
# passes settings.SCRAPE_HTML_MAX_MB; this default keeps direct/test callers safe.
_DEFAULT_HTML_MAX_BYTES = 5 * 1024 * 1024

# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------


@dataclass
class ScrapeResult:
    """Metadata extracted from a URL scrape.

    Empty/None fields indicate the data was unavailable or scraping was blocked.
    """

    url: str
    domain: str
    title: str | None = None
    description: str | None = None
    creator_name: str | None = None
    creator_profile_url: str | None = None
    source_site: str | None = None
    license: str | None = None
    # Image URLs (public, no auth required)
    image_urls: list[str] = field(default_factory=list)
    # Raw tag strings from the page (unmapped; caller does reconciliation)
    raw_tags: list[str] = field(default_factory=list)
    # Whether scraping was blocked by robots.txt or a policy decision
    blocked: bool = False
    # Human-readable reason if blocked=True or metadata was incomplete
    note: str | None = None


# ---------------------------------------------------------------------------
# robots.txt cache (in-process, per worker invocation)
# ---------------------------------------------------------------------------

_robots_cache: dict[str, RobotFileParser] = {}
_ROBOTS_UA = "PartFolder3D/1 (+https://github.com/crzykidd/partfolder3d)"


def _get_robots(domain: str, timeout: int = 10) -> RobotFileParser | None:
    """Return a parsed RobotFileParser for the domain, or None on error."""
    if domain in _robots_cache:
        return _robots_cache[domain]

    robots_url = f"https://{domain}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        resp = guarded_fetch(
            robots_url,
            max_bytes=_ROBOTS_MAX_BYTES,
            timeout=timeout,
            headers={"User-Agent": _ROBOTS_UA},
        )
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        # else: no robots.txt or blocked → conservative: allow
    except (SSRFBlockedError, GuardedFetchError, httpx.HTTPError):
        log.debug(
            "robots.txt fetch failed for %s (treating as allow-all)",
            sanitize_for_log(domain),
        )
    _robots_cache[domain] = rp
    return rp


def _robots_allows(domain: str, path: str) -> bool:
    """Return True if robots.txt allows fetching the given path."""
    rp = _get_robots(domain)
    if rp is None:
        return True
    return rp.can_fetch(_ROBOTS_UA, path)


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _og(tree: object, prop: str) -> str | None:
    """Extract an Open Graph property value from a parsed HTML tree."""
    # selectolax CSS selector: meta[property="og:..."]
    try:
        node = tree.css_first(f'meta[property="{prop}"]')  # type: ignore[union-attr]
        if node is not None:
            return node.attributes.get("content")
    except Exception:
        pass
    return None


def _meta_name(tree: object, name: str) -> str | None:
    """Extract a <meta name="..."> content value."""
    try:
        node = tree.css_first(f'meta[name="{name}"]')  # type: ignore[union-attr]
        if node is not None:
            return node.attributes.get("content")
    except Exception:
        pass
    return None


def _parse_html(html: str) -> object | None:
    """Parse HTML text; returns selectolax HTMLParser or None on failure."""
    try:
        from selectolax.parser import HTMLParser  # noqa: PLC0415
        return HTMLParser(html)
    except ImportError:
        log.warning("selectolax not installed; HTML parsing unavailable")
    except Exception:
        log.debug("HTML parse failed")
    return None


def _extract_images(tree: object, base_url: str, max_images: int) -> list[str]:
    """Extract candidate image URLs from OG tags and <img> tags."""
    seen: list[str] = []
    # Open Graph images first (highest quality, explicitly curated)
    for meta in tree.css('meta[property="og:image"]'):  # type: ignore[union-attr]
        src = meta.attributes.get("content", "")
        if src and src not in seen:
            seen.append(src)
    # Fallback: regular img tags with a reasonable minimum size heuristic
    if len(seen) < max_images:
        for img in tree.css("img"):  # type: ignore[union-attr]
            src = img.attributes.get("src", "") or img.attributes.get("data-src", "")
            if not src:
                continue
            absolute = urljoin(base_url, src)
            if absolute.startswith("http") and absolute not in seen:
                seen.append(absolute)
                if len(seen) >= max_images:
                    break
    return seen[:max_images]


def _extract_tags(tree: object) -> list[str]:
    """Extract tags from meta keywords, JSON-LD, or common site-specific patterns."""
    raw: list[str] = []

    # Standard meta keywords
    kw = _meta_name(tree, "keywords")
    if kw:
        for t in re.split(r"[,;]", kw):
            t = t.strip()
            if t:
                raw.append(t)

    # JSON-LD: look for "keywords" arrays in structured data
    for script in tree.css('script[type="application/ld+json"]'):  # type: ignore[union-attr]
        text = script.text() if callable(getattr(script, "text", None)) else ""
        if not text:
            continue
        try:
            import json  # noqa: PLC0415
            data = json.loads(text)
            kws = data.get("keywords", [])
            if isinstance(kws, str):
                kws = [k.strip() for k in kws.split(",")]
            if isinstance(kws, list):
                for k in kws:
                    k = str(k).strip()
                    if k and k not in raw:
                        raw.append(k)
        except Exception:
            pass

    return raw[:50]  # cap at 50 raw tags; reconciliation filters further


# ---------------------------------------------------------------------------
# Main scrape function
# ---------------------------------------------------------------------------


def scrape_url(
    url: str,
    timeout: int = 15,
    max_images: int = 20,
    html_max_bytes: int = _DEFAULT_HTML_MAX_BYTES,
) -> ScrapeResult:
    """Scrape public metadata from a URL.

    Returns a ScrapeResult; never raises.  Errors set result.note.

    Robots.txt is checked before fetching.  If blocked, returns immediately
    with result.blocked=True.

    Files are never auto-downloaded; only metadata and image URLs are returned.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    result = ScrapeResult(url=url, domain=domain)

    _safe_url = sanitize_for_log(url)

    # SSRF guard — reject URLs resolving to internal/link-local/cloud-metadata IPs.
    # (The guarded fetch below re-validates every hop; this pre-flight gives a
    # friendlier note and short-circuits before the robots.txt fetch.)
    try:
        assert_safe_url(url)
    except SSRFBlockedError as exc:
        result.blocked = True
        result.note = str(exc)
        log.warning("scrape_url: SSRF guard blocked %s: %s", _safe_url, exc)
        return result

    # robots.txt check
    if not _robots_allows(domain, parsed.path or "/"):
        result.blocked = True
        result.note = f"robots.txt disallows fetching {url}"
        log.info("scrape_url: robots.txt blocked %s", _safe_url)
        return result

    try:
        # Guarded fetch: no auto-redirects (each hop re-validated), body streamed
        # and aborted once html_max_bytes is exceeded (no unbounded resp.text).
        resp = guarded_fetch(
            url,
            max_bytes=html_max_bytes,
            timeout=timeout,
            headers={
                "User-Agent": _ROBOTS_UA,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )

        if resp.status_code != 200:
            result.note = f"HTTP {resp.status_code}"
            # Anti-bot / access-denied codes (Cloudflare et al. answer 403 with a
            # "Just a moment" JS challenge) mean a smarter fetcher might succeed —
            # flag as blocked so the AgentQL fallback (if enabled) is triggered.
            # 404/500-class stay unblocked (a fallback wouldn't help).
            if resp.status_code in (401, 403, 429, 503):
                result.blocked = True
            return result

        content_type = resp.content_type
        if "html" not in content_type:
            result.note = f"Non-HTML response: {content_type}"
            return result

        html = resp.text

    except SSRFBlockedError as exc:
        # A redirect hop pointed at an internal/blocked target.
        result.blocked = True
        result.note = str(exc)
        log.warning("scrape_url: SSRF guard blocked redirect for %s: %s", _safe_url, exc)
        return result
    except GuardedFetchError as exc:
        result.note = f"Scrape error: {exc}"
        log.warning("scrape_url: guarded fetch failed for %s: %s", _safe_url, exc)
        return result
    except httpx.TimeoutException:
        result.note = "Scrape timed out"
        log.info("scrape_url: timeout for %s", _safe_url)
        return result
    except Exception as exc:
        result.note = f"Scrape error: {exc}"
        log.warning("scrape_url: error for %s: %s", _safe_url, exc)
        return result

    tree = _parse_html(html)
    if tree is None:
        result.note = "HTML parse failed"
        return result

    # Title: OG → <title>
    result.title = (
        _og(tree, "og:title")
        or (_meta_name(tree, "title"))
    )
    if not result.title:
        try:
            title_node = tree.css_first("title")  # type: ignore[union-attr]
            if title_node:
                result.title = (title_node.text() or "").strip() or None
        except Exception:
            pass

    # Description
    result.description = (
        _og(tree, "og:description")
        or _meta_name(tree, "description")
    )

    # Site name
    result.source_site = _og(tree, "og:site_name") or domain

    # Images
    result.image_urls = _extract_images(tree, url, max_images)

    # Tags
    result.raw_tags = _extract_tags(tree)

    # Creator: look for common author meta patterns
    result.creator_name = (
        _meta_name(tree, "author")
        or _meta_name(tree, "article:author")
        or _og(tree, "article:author")
    )

    # License: try to find a cc/license link or meta
    for a in tree.css('a[rel="license"], link[rel="license"]'):  # type: ignore[union-attr]
        href = a.attributes.get("href", "")
        if href:
            result.license = href
            break

    log.debug(
        "scrape_url: %s → title=%r images=%d tags=%d",
        _safe_url, result.title, len(result.image_urls), len(result.raw_tags),
    )
    return result


# ---------------------------------------------------------------------------
# Domain extraction helper
# ---------------------------------------------------------------------------


def extract_domain(url: str) -> str:
    """Extract the registrable domain (without www.) from a URL."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain
