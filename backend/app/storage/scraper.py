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
from urllib.parse import parse_qs, unquote, urljoin, urlparse
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
# Cap on the __NEXT_DATA__ blob before JSON-parsing it (the HTML itself is already
# capped by the caller, but the blob may still be large; guard separately).
_NEXT_DATA_MAX_BYTES = 5 * 1024 * 1024

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


# ---------------------------------------------------------------------------
# Text cleanup helpers (SEO boilerplate stripping) — issue #27
# ---------------------------------------------------------------------------

# Trailing " - Something.com" / " | Something.com" site-name suffix (title only).
# Kept conservative: the leading separator must be surrounded by whitespace, and
# the site segment must not contain another separator, so we only strip a genuine
# trailing "<sep> <Site>.<tld>" tail — never legitimate mid-title content.
_SITE_SUFFIX_RE = re.compile(
    r"\s+[-–—|]\s+[^|\-–—]*\.(?:com|net|org|io|co)\s*$",
    re.IGNORECASE,
)


def _strip_pipe_boilerplate(text: str | None) -> str | None:
    """Strip site SEO boilerplate that follows the first ' | ' separator.

    Aggregator sites (Printables/MakerWorld/Thingiverse) bake share-card
    boilerplate into their OG tags after a ' | ' pipe, e.g.
    "NeilMed Sinus Rinse holder by Fuu | Download free STL model | Printables.com".
    We keep only the leading segment.  Conservative: the separator must be a
    space-padded pipe so we never split on a bare '|' inside real content.
    """
    if not text:
        return text
    cleaned = text.split(" | ", 1)[0].strip()
    return cleaned or None


def _clean_title(title: str | None) -> str | None:
    """Strip after-pipe boilerplate and a trailing ' - <Site>.com' suffix."""
    cleaned = _strip_pipe_boilerplate(title)
    if not cleaned:
        return None
    cleaned = _SITE_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned or None


def _clean_description(desc: str | None) -> str | None:
    """Strip trailing SEO boilerplate that follows a ' | ' separator."""
    return _strip_pipe_boilerplate(desc)


def _creator_from_title(title: str | None) -> str | None:
    """Best-effort creator from the "<name> by <Creator>" title pattern.

    Printables titles read "<Model title> by <Creator> | <boilerplate>".
    Conservative: only fires when the leading (pre-pipe) segment contains a
    space-padded ' by '; takes the text after the last such ' by ' and rejects
    absurdly long captures.  Returns None when the pattern doesn't clearly match.
    """
    if not title:
        return None
    first_seg = title.split(" | ", 1)[0]
    if " by " not in first_seg:
        return None
    candidate = first_seg.rsplit(" by ", 1)[1].strip()
    if candidate and len(candidate) <= 80:
        return candidate
    return None


# ---------------------------------------------------------------------------
# Image selection helpers — issue #28
# ---------------------------------------------------------------------------


def _srcset_largest(srcset: str) -> str | None:
    """Return the highest-resolution URL from a srcset attribute.

    srcset format: "url1 320w, url2 640w" (width descriptors) or
    "url1 1x, url2 2x" (density descriptors).  Prefers the largest width
    descriptor; falls back to the largest density; then the first entry.
    """
    if not srcset:
        return None
    best_url: str | None = None
    best_w = -1
    best_density = -1.0
    first_url: str | None = None
    for part in srcset.split(","):
        tokens = part.strip().split()
        if not tokens:
            continue
        url = tokens[0]
        if first_url is None:
            first_url = url
        descriptor = tokens[1] if len(tokens) > 1 else ""
        if descriptor.endswith("w"):
            try:
                w = int(descriptor[:-1])
            except ValueError:
                continue
            if w > best_w:
                best_w = w
                best_url = url
        elif descriptor.endswith("x"):
            try:
                d = float(descriptor[:-1])
            except ValueError:
                continue
            # Only let density win while no width descriptor has been seen.
            if best_w < 0 and d > best_density:
                best_density = d
                best_url = url
    return best_url or first_url


def _parse_url_width(url: str) -> int | None:
    """Return the pixel width hint encoded in a URL, or None if not detectable.

    Recognises:
      - ``x-oss-process=image/resize,...,w_N,...``  (Alibaba OSS CDN; raw or
        URL-encoded value — e.g. ``image%2Fresize%2Cw_100``).
      - ``?w=N``  or  ``&w=N``  query param.
      - ``?width=N``  or  ``&width=N``  query param.

    Returns ``None`` when no width hint is found — the caller keeps the URL.
    Never raises.
    """
    try:
        parsed = urlparse(url)
        qs_raw = parsed.query
        if not qs_raw:
            return None
        # URL-decode the full query string so both raw and percent-encoded OSS
        # process params ("image%2Fresize%2Cw_100") normalise to the same form.
        qs_decoded = unquote(qs_raw)

        # Alibaba OSS: x-oss-process=image/resize[,...,]w_N[,...]
        m = re.search(r"x-oss-process=image/resize[^&]*\bw_(\d+)", qs_decoded)
        if m:
            return int(m.group(1))

        # Plain ?w=N or ?width=N
        params = parse_qs(qs_raw)
        for key in ("w", "width"):
            vals = params.get(key) or []
            if vals:
                try:
                    return int(vals[0])
                except ValueError:
                    pass
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
    """Extract candidate image URLs, preferring full-resolution over og:image.

    On MakerWorld/Printables/Thingiverse the ``og:image`` is the social-share
    card — cropped/downscaled to ~1200x630 — not the full-res gallery photo
    (issue #28).  We therefore rank candidates by likely resolution and keep
    ``og:image`` only as a fallback so the default (first) image is full-res:

      1. ``<img srcset>`` / ``<source srcset>`` — largest width descriptor.
      2. Lazy-loaded full-size ``data-src`` / ``data-original`` / ``data-full``.
      3. ``og:image`` — reliable but often a downscaled social card.
      4. Plain ``<img src>`` — lowest priority (may be thumbnails/placeholders).

    Buckets are concatenated in that order, de-duplicated preserving first
    occurrence, then capped at ``max_images``.
    """
    srcset_imgs: list[str] = []
    lazy_imgs: list[str] = []
    og_imgs: list[str] = []
    plain_imgs: list[str] = []

    # 1. srcset (img + source): the largest-width candidate per element.
    for node in tree.css("img[srcset], source[srcset]"):  # type: ignore[union-attr]
        best = _srcset_largest(node.attributes.get("srcset") or "")
        if best:
            srcset_imgs.append(best)

    # 2/4. <img> lazy full-size attrs (high) and plain src (low).
    for img in tree.css("img"):  # type: ignore[union-attr]
        attrs = img.attributes
        lazy = (
            attrs.get("data-src")
            or attrs.get("data-original")
            or attrs.get("data-full")
        )
        if lazy:
            lazy_imgs.append(lazy)
        src = attrs.get("src")
        if src:
            plain_imgs.append(src)

    # 3. og:image — fallback only (curated but usually a downscaled social card).
    for meta in tree.css('meta[property="og:image"]'):  # type: ignore[union-attr]
        content = meta.attributes.get("content")
        if content:
            og_imgs.append(content)

    seen_bases: set[str] = set()
    seen: list[str] = []
    for bucket in (srcset_imgs, lazy_imgs, og_imgs, plain_imgs):
        for src in bucket:
            absolute = urljoin(base_url, src.strip())
            if not absolute.startswith("http"):
                continue

            parsed_abs = urlparse(absolute)

            # Drop comment-section images (path-segment heuristic; keeps URLs
            # whose path contains only "comment" as part of a model slug).
            abs_path = parsed_abs.path
            if "/comment/" in abs_path or "/comments/" in abs_path:
                continue

            # Drop tiny width variants (width hint < 400 px).  No hint → keep.
            w = _parse_url_width(absolute)
            if w is not None and w < 400:
                continue

            # Dedupe by base URL (scheme + netloc + path), ignoring query
            # string — catches the og:image ?w=1200 vs gallery ?w=1000 pair.
            base_key = f"{parsed_abs.scheme}://{parsed_abs.netloc}{parsed_abs.path}"
            if base_key in seen_bases:
                continue
            seen_bases.add(base_key)
            seen.append(absolute)
            if len(seen) >= max_images:
                return seen
    return seen


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
# Next.js __NEXT_DATA__ enrichment helper
# ---------------------------------------------------------------------------


def _enrich_from_next_data(result: ScrapeResult, html: str, max_images: int) -> None:
    """Best-effort enrichment from a Next.js ``__NEXT_DATA__`` embedded JSON blob.

    Handles the MakerWorld shape (``props.pageProps.design.*``); silently
    does nothing for other sites whose NEXT_DATA has a different structure.
    Shape-gated, not domain-gated — regional/mirror domains still benefit.

    Priority rules:
      - ``design.title`` *replaces* the og:title-derived title (it's the
        unsuffixed clean title); still run through ``_clean_title``.
      - ``designCreator.name`` and ``designCreator.handle`` / profile URL are
        used **only** when the existing meta/title heuristics found nothing
        (existing signals always win for creator fields).
      - ``categories[].name`` are appended to ``raw_tags``; dupes skipped.
      - ``designExtension.design_pictures[].url`` — when present (≥1 entry),
        the full ordered gallery *replaces* ``result.image_urls`` (DOM-scraped
        images are discarded).  ``coverUrl`` is kept first if it differs from
        ``pictures[0]``.  These are clean base URLs with no resize params.

    Never raises.  A malformed/huge JSON blob is silently ignored.
    """
    try:
        import json  # noqa: PLC0415

        # Locate the script tag by id without re-running the full HTML parser.
        marker = '<script id="__NEXT_DATA__"'
        start = html.find(marker)
        if start == -1:
            return

        tag_end = html.find(">", start)
        if tag_end == -1:
            return
        script_end = html.find("</script>", tag_end)
        if script_end == -1:
            return

        blob = html[tag_end + 1 : script_end]
        if len(blob) > _NEXT_DATA_MAX_BYTES:
            log.debug(
                "_enrich_from_next_data: blob too large (%d bytes), skipping",
                len(blob),
            )
            return

        data = json.loads(blob)

        # Navigate to MakerWorld's design node; harmless on other shapes.
        design = (
            data.get("props", {})
            .get("pageProps", {})
            .get("design")
        )
        if not isinstance(design, dict):
            return

        # 1. Clean title — prefer NEXT_DATA's unsuffixed title over og:title.
        nd_title = design.get("title")
        if isinstance(nd_title, str) and nd_title.strip():
            cleaned = _clean_title(nd_title)
            if cleaned:
                result.title = cleaned

        # 2 & 3. Creator name + profile URL — fallback only.
        creator = design.get("designCreator")
        if isinstance(creator, dict):
            if not result.creator_name:
                nd_name = creator.get("name")
                if isinstance(nd_name, str) and nd_name.strip():
                    result.creator_name = nd_name.strip()
            if not result.creator_profile_url:
                nd_handle = creator.get("handle")
                if isinstance(nd_handle, str) and nd_handle.strip():
                    result.creator_profile_url = (
                        f"https://makerworld.com/en/@{nd_handle.strip()}"
                    )

        # 4. Categories → additional tags (dedupe, cap at 50).
        categories = design.get("categories")
        if isinstance(categories, list):
            existing_lower = {t.lower() for t in result.raw_tags}
            for cat in categories:
                if isinstance(cat, dict):
                    cat_name = cat.get("name")
                elif isinstance(cat, str):
                    cat_name = cat
                else:
                    continue
                if isinstance(cat_name, str) and cat_name.strip():
                    norm = cat_name.strip()
                    if norm.lower() not in existing_lower:
                        result.raw_tags.append(norm)
                        existing_lower.add(norm.lower())
            result.raw_tags = result.raw_tags[:50]

        # 5. Authoritative gallery from designExtension.design_pictures[].url.
        #    When present, REPLACES DOM-scraped image_urls entirely — these are
        #    clean full-res base URLs with no resize params.
        ext = design.get("designExtension")
        if isinstance(ext, dict):
            pictures = ext.get("design_pictures")
            if isinstance(pictures, list) and pictures:
                gallery_urls: list[str] = []
                for pic in pictures:
                    if isinstance(pic, dict):
                        u = pic.get("url")
                    elif isinstance(pic, str):
                        u = pic
                    else:
                        continue
                    if isinstance(u, str) and u.strip().startswith("http"):
                        gallery_urls.append(u.strip())
                if gallery_urls:
                    # Honour coverUrl ordering: put it first when it differs
                    # from picture[0] (they're usually the same, but be safe).
                    cover = design.get("coverUrl")
                    if (
                        isinstance(cover, str)
                        and cover.strip()
                        and cover.strip() != gallery_urls[0]
                    ):
                        cover_clean = cover.strip()
                        # Remove cover from its current position if present,
                        # then prepend so it's always first.
                        gallery_urls = [cover_clean] + [
                            u for u in gallery_urls if u != cover_clean
                        ]
                    result.image_urls = gallery_urls[:max_images]

    except Exception:
        log.debug("_enrich_from_next_data: failed to parse NEXT_DATA (ignored)")


# ---------------------------------------------------------------------------
# Shared HTML → ScrapeResult extraction helper
# ---------------------------------------------------------------------------


def extract_metadata_from_html(
    html: str,
    url: str,
    domain: str,
    max_images: int,
) -> ScrapeResult:
    """Parse resolved HTML into a ScrapeResult (title/desc/images/tags/creator/license).

    Used by both the static scraper (scrape_url) and HTML-returning fallback
    backends (FlareSolverr) so they all produce identical metadata extraction.

    Returns a ScrapeResult; never raises.  On parse failure sets result.note
    and returns an empty result (blocked=False — the HTTP call succeeded; only
    the HTML parse failed).
    """
    result = ScrapeResult(url=url, domain=domain)

    tree = _parse_html(html)
    if tree is None:
        result.note = "HTML parse failed"
        return result

    # Title: OG → <title>.  Keep the raw title for creator extraction (the
    # "<name> by <Creator>" pattern lives before the boilerplate pipe), then
    # strip SEO boilerplate for the user-facing value (issue #27).
    raw_title = (
        _og(tree, "og:title")
        or (_meta_name(tree, "title"))
    )
    if not raw_title:
        try:
            title_node = tree.css_first("title")  # type: ignore[union-attr]
            if title_node:
                raw_title = (title_node.text() or "").strip() or None
        except Exception:
            pass
    result.title = _clean_title(raw_title)

    # Description (strip trailing " | ..." boilerplate — issue #27)
    result.description = _clean_description(
        _og(tree, "og:description")
        or _meta_name(tree, "description")
    )

    # Site name
    result.source_site = _og(tree, "og:site_name") or domain

    # Images
    result.image_urls = _extract_images(tree, url, max_images)

    # Tags
    result.raw_tags = _extract_tags(tree)

    # Creator name: common author meta patterns, then fall back to the
    # "<name> by <Creator>" title pattern (Printables exposes no author meta
    # but shows the creator in the title) — issue #27.
    name = (
        _meta_name(tree, "author")
        or _meta_name(tree, "article:author")
        or _og(tree, "article:author")
    )
    # article:author is sometimes a profile URL rather than a display name;
    # that belongs in creator_profile_url, not the name.
    if name and name.strip().lower().startswith("http"):
        name = None
    if not name:
        name = _creator_from_title(raw_title)
    result.creator_name = (name or "").strip() or None

    # Creator profile URL: previously modeled but never assigned (issue #27).
    # Best-effort from rel=author links/anchors or a URL-valued article:author.
    profile_url: str | None = None
    for sel in ('link[rel="author"]', 'a[rel="author"]'):
        try:
            node = tree.css_first(sel)  # type: ignore[union-attr]
        except Exception:
            node = None
        if node is not None:
            href = (node.attributes.get("href") or "").strip()
            if href:
                absolute = urljoin(url, href)
                if absolute.startswith("http"):
                    profile_url = absolute
                    break
    if not profile_url:
        author_meta = (
            _og(tree, "article:author") or _meta_name(tree, "article:author") or ""
        ).strip()
        if author_meta.lower().startswith("http"):
            profile_url = author_meta
    result.creator_profile_url = profile_url

    # License: try to find a cc/license link or meta
    for a in tree.css('a[rel="license"], link[rel="license"]'):  # type: ignore[union-attr]
        href = a.attributes.get("href", "")
        if href:
            result.license = href
            break

    # Next.js __NEXT_DATA__ enrichment (MakerWorld et al.).  Runs last so
    # existing meta signals already populate the result — creator fields are
    # only filled in when still empty; the clean NEXT_DATA title overrides the
    # og:title-suffixed one; design_pictures gallery replaces DOM-scraped images.
    _enrich_from_next_data(result, html, max_images)

    return result


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

    result = extract_metadata_from_html(html, url, domain, max_images)
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
