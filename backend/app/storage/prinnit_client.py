"""prinnit.com metadata connector.

prinnit.com is a paid 3D-model marketplace whose design pages are a
client-rendered React SPA with no Open Graph tags, so the generic
``scrape_url`` sees only an empty shell and produces a garbage title. This
module fetches the SAME metadata (title/description/creator/tags/gallery
images/print details) from prinnit's public, no-auth JSON API instead.

The gated ``.3mf`` file itself is never touched here — only metadata and
public ``images.prinnit.com`` image URLs are returned; the user still
downloads the file after purchase and uploads it in the wizard.

Resolution flow (all GET, no auth, ``api.prinnit.com``) — reverse-engineered,
not derivable from any public docs (see docs/decisions.md):

  1. ``GET /designers`` -> ``{"designers": [{sub, designerName, ...}, ...]}``.
     Matched case-insensitively against the URL's ``<DesignerName>`` segment
     (the site itself lowercases for lookups).
  2. ``GET /designs/<sub>`` -> a JSON array of *that designer's entire design
     catalog* (currently ~137 items / ~1.2 MB for the reference designer).
     There is no per-design public endpoint — every other shape
     (``/design/<id>``, ``/v1/...``) returns an AWS API-Gateway 403
     ``{"message": "Missing Authentication Token"}``, i.e. route-not-found.
     The whole list is fetched once per import and scanned for ``designId``.

Both requests go through :func:`app.storage.ssrf_guard.guarded_fetch` (the
same SSRF-hardened chokepoint the rest of the scraper uses) with byte caps.

Design (docs/decisions.md): this is intentionally a *pure function* that
returns an enriched ``ScrapeResult`` rather than a full session-populating
connector like the Manyfold one — prinnit needs no auth, no DB-backed
instance config, and downloads no files, so the existing downstream
image/tag/creator population code in ``process_import_session`` is the right
place for images to land as normal ``is_url`` rows.
"""

from __future__ import annotations

import html
import json
import logging
import re
from urllib.parse import urlparse

from .scraper import ScrapeResult
from .ssrf_guard import GuardedFetchError, SSRFBlockedError, guarded_fetch, sanitize_for_log

log = logging.getLogger(__name__)

_API_BASE = "https://api.prinnit.com"

# /designers currently returns 3 designers; a few hundred KB would already be
# generous. Capped well above that so ordinary growth doesn't trip it, but
# still bounded (SSRF/DoS defense — same byte-cap pattern as scraper.py).
_DESIGNERS_MAX_BYTES = 2 * 1024 * 1024

# /designs/<sub> is the ONE public per-designer endpoint and returns the
# designer's ENTIRE catalog (currently ~137 items / ~1.2 MB for the reference
# designer) — the app itself loads the whole list and indexes client-side.
# Capped generously above the observed size.
_DESIGNS_MAX_BYTES = 10 * 1024 * 1024

_UA = "PartFolder3D/1 (+https://github.com/crzykidd/partfolder3d)"

# https://prinnit.com/<DesignerName>/design/<designId>
_DESIGN_URL_RE = re.compile(r"^/(?P<designer>[^/]+)/design/(?P<design_id>[^/?#]+)/?$")


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


def _parse_design_url(url: str) -> tuple[str, str] | None:
    """Parse a prinnit design URL into ``(designer_name, design_id)``.

    Returns ``None`` for anything that isn't a ``prinnit.com`` design page —
    wrong domain, or a path that doesn't match the
    ``/<Designer>/design/<id>`` shape (e.g. a store/profile page). The caller
    falls through to the generic scrape path in that case.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    domain = (parsed.netloc or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain != "prinnit.com":
        return None

    match = _DESIGN_URL_RE.match(parsed.path or "")
    if not match:
        return None

    designer_name = match.group("designer").strip()
    design_id = match.group("design_id").strip()
    if not designer_name or not design_id:
        return None
    return designer_name, design_id


# ---------------------------------------------------------------------------
# API fetch helpers
# ---------------------------------------------------------------------------


def _fetch_json(url: str, *, timeout: float, max_bytes: int) -> object | None:
    """GET *url* and parse the JSON body. Returns ``None`` on any failure.

    Never raises — SSRF blocks, transport errors, non-200 responses, and
    malformed JSON are all logged and turned into ``None`` so the caller can
    fall through to the generic scrape path.
    """
    try:
        resp = guarded_fetch(
            url,
            max_bytes=max_bytes,
            timeout=timeout,
            headers={"User-Agent": _UA, "Accept": "application/json"},
        )
    except (SSRFBlockedError, GuardedFetchError) as exc:
        log.info("prinnit_client: fetch failed for %s: %s", sanitize_for_log(url), exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive; never raises upward
        log.warning(
            "prinnit_client: unexpected fetch error for %s: %s",
            sanitize_for_log(url), exc,
        )
        return None

    if resp.status_code != 200:
        log.info(
            "prinnit_client: HTTP %s for %s", resp.status_code, sanitize_for_log(url)
        )
        return None

    try:
        return json.loads(resp.text)
    except (ValueError, TypeError):
        log.info("prinnit_client: non-JSON response from %s", sanitize_for_log(url))
        return None


def _find_designer_sub(designers_payload: object, designer_name: str) -> str | None:
    """Case-insensitive lookup of a designer's Cognito ``sub`` by ``designerName``.

    Never assumes ordering — the site is small today (3 designers) but this
    always matches by name.
    """
    if not isinstance(designers_payload, dict):
        return None
    designers = designers_payload.get("designers")
    if not isinstance(designers, list):
        return None

    target = designer_name.strip().lower()
    for entry in designers:
        if not isinstance(entry, dict):
            continue
        name = entry.get("designerName")
        if isinstance(name, str) and name.strip().lower() == target:
            sub = entry.get("sub")
            if isinstance(sub, str) and sub:
                return sub
    return None


def _find_design(designs_payload: object, design_id: str) -> dict | None:  # type: ignore[type-arg]
    """Find the design dict whose ``designId`` matches within a designer's full list."""
    if not isinstance(designs_payload, list):
        return None
    for entry in designs_payload:
        if isinstance(entry, dict) and entry.get("designId") == design_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------


def _extract_image_urls(design: dict, max_images: int) -> list[str]:  # type: ignore[type-arg]
    """Ordered, de-duped gallery: ``photosUrls[].original`` then description photos.

    ``descriptionPhotosUrls`` is observed (reference fixture) as a plain
    ``list[str]`` of URLs directly — not a list of ``{"original": ...}``
    objects like ``photosUrls`` — so both shapes are handled defensively.
    """
    urls: list[str] = []
    seen: set[str] = set()

    def _add(candidate: object) -> None:
        if isinstance(candidate, dict):
            candidate = candidate.get("original")
        if isinstance(candidate, str):
            candidate = candidate.strip()
            if candidate.startswith("http") and candidate not in seen:
                seen.add(candidate)
                urls.append(candidate)

    photos = design.get("photosUrls")
    if isinstance(photos, list):
        for p in photos:
            _add(p)

    description_photos = design.get("descriptionPhotosUrls")
    if isinstance(description_photos, list):
        for p in description_photos:
            _add(p)

    return urls[:max_images]


# Block-level tags whose boundary must become a line break so paragraphs and
# list items don't collapse into one blob. Matched as open OR close tags.
_BLOCK_BOUNDARY_RE = re.compile(
    r"</?\s*(?:p|div|br|li|ul|ol|h[1-6]|blockquote|tr|table|section|article)\b[^>]*>",
    re.IGNORECASE,
)
# <img> is dropped entirely (we never keep image URLs from the description).
_IMG_TAG_RE = re.compile(r"<\s*img\b[^>]*>", re.IGNORECASE)
# Any remaining tag (e.g. <strong>, <a>, <em>, <span>) is stripped in place.
_ANY_TAG_RE = re.compile(r"<[^>]+>")
# 3+ consecutive newlines (allowing intervening spaces) collapse to exactly 2.
_EXCESS_NEWLINES_RE = re.compile(r"\n[ \t]*\n[ \t]*(?:\n[ \t]*)+")


def _html_to_text(raw: str) -> str:
    """Convert prinnit's HTML ``description`` to readable plain text.

    Why: the frontend renders ``session.description`` as a plain-text node
    everywhere (wizard textarea, item page, public share page) — there is no
    HTML-rendering path anywhere in ``frontend/src`` (see docs/decisions.md).
    Passing the raw HTML through would show literal ``<p>``/``<strong>`` tags
    to the user, so we flatten it here.

    Rules:
      - Block-level tag boundaries (``</p>``, ``<br>``, ``</li>``, headings, …)
        become newlines so paragraph/list breaks survive.
      - ``<img>`` is dropped entirely (image URLs are never kept from the
        description; the gallery comes from ``photosUrls``).
      - All remaining inline tags (``<strong>``, ``<a>``, …) are stripped.
      - HTML entities (``&amp;``, ``&quot;``, ``&#39;``, …) are unescaped.
      - 3+ consecutive newlines collapse to 2; leading/trailing whitespace and
        trailing spaces on each line are trimmed.

    Never raises; on any failure returns ``""`` (caller treats as no description).
    """
    if not raw:
        return ""
    try:
        text = _IMG_TAG_RE.sub("", raw)
        text = _BLOCK_BOUNDARY_RE.sub("\n", text)
        text = _ANY_TAG_RE.sub("", text)
        text = html.unescape(text)
        # Trim trailing spaces on each line, then collapse runs of blank lines.
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        text = _EXCESS_NEWLINES_RE.sub("\n\n", text)
        return text.strip()
    except Exception:  # pragma: no cover - defensive; never raises upward
        log.debug("_html_to_text: conversion failed (ignored)")
        return ""


def _format_print_time(minutes: object) -> str | None:
    """Render a minutes value as e.g. "35h 17m".

    NOTE (owner-flagged assumption, docs/decisions.md): ``printTime`` appears
    to be minutes based on the reference fixture (2117 -> "35h 17m" for a
    moderately complex print); this is not confirmed against prinnit's own
    UI. If prinnit ever changes/clarifies the unit, this is the one place to
    fix.
    """
    try:
        total_minutes = int(minutes)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if total_minutes < 0:
        return None
    hours, mins = divmod(total_minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def _format_weight(weight: object) -> str | None:
    if not isinstance(weight, int | float) or weight <= 0:
        return None
    if isinstance(weight, float) and weight != int(weight):
        return f"{weight:g} g"
    return f"{int(weight)} g"


def _build_print_details_block(design: dict) -> str:  # type: ignore[type-arg]
    """Build a compact, human-readable print-details block for the description.

    Only includes fields present on the design object (never invents data).
    Rendered as plain text, not HTML: the wizard/item pages render
    ``description`` as a plain text node everywhere (no
    ``dangerouslySetInnerHTML``/sanitizer exists in the frontend), so an
    HTML fragment would show up as literal ``<p>``/``<li>`` tags rather than
    formatted markup — see docs/decisions.md.
    """
    lines: list[str] = []

    formatted_time = _format_print_time(design.get("printTime"))
    if formatted_time:
        lines.append(f"Print time: {formatted_time}")

    difficulty = design.get("printDifficulty")
    if isinstance(difficulty, str) and difficulty.strip():
        lines.append(f"Difficulty: {difficulty.strip().title()}")

    formatted_weight = _format_weight(design.get("weight"))
    if formatted_weight:
        lines.append(f"Weight: {formatted_weight}")

    dims = design.get("minPrinterDimensions")
    if isinstance(dims, dict) and all(k in dims for k in ("x", "y", "z")):
        lines.append(
            f"Min. printer bed: {dims['x']} x {dims['y']} x {dims['z']} mm"
        )

    printing_flags: list[str] = []
    if design.get("isMultiColor"):
        printing_flags.append("multi-color")
    if design.get("amsRequired"):
        printing_flags.append("AMS required")
    if printing_flags:
        lines.append(f"Printing: {', '.join(printing_flags)}")

    filaments = design.get("filaments")
    if isinstance(filaments, list) and filaments:
        filament_labels: list[str] = []
        for fil in filaments:
            if not isinstance(fil, dict):
                continue
            brand = str(fil.get("brandName") or "").strip()
            product = str(fil.get("productName") or "").strip()
            ftype = str(fil.get("filamentType") or "").strip()
            label = " ".join(part for part in (brand, product) if part)
            if ftype:
                label = f"{label} ({ftype})" if label else ftype
            if label:
                filament_labels.append(label)
        if filament_labels:
            lines.append(f"Filaments used: {', '.join(filament_labels)}")

    video_url = design.get("videoUrl")
    if isinstance(video_url, str) and video_url.strip().startswith("http"):
        lines.append(f"Video: {video_url.strip()}")

    if not lines:
        return ""

    return "Print details:\n" + "\n".join(f"- {line}" for line in lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def scrape_prinnit(
    url: str,
    *,
    timeout: int = 15,
    max_images: int = 20,
) -> ScrapeResult | None:
    """Scrape a prinnit.com design page via prinnit's public JSON API.

    Returns ``None`` when *url* isn't a prinnit design URL, or the designer
    or design can't be resolved (unknown designer, unknown ``designId``, or
    any HTTP/parse failure) — the caller falls through to the generic
    ``scrape_url`` path. Never raises (mirrors ``scrape_url``'s contract).

    Only metadata and public ``images.prinnit.com`` image URLs are fetched;
    the gated ``.3mf`` file is never downloaded here.
    """
    try:
        return _scrape_prinnit_inner(url, timeout=timeout, max_images=max_images)
    except Exception as exc:  # pragma: no cover - defensive; never raises upward
        log.warning(
            "scrape_prinnit: unexpected error for %s: %s", sanitize_for_log(url), exc
        )
        return None


def _scrape_prinnit_inner(
    url: str, *, timeout: int, max_images: int
) -> ScrapeResult | None:
    parsed_target = _parse_design_url(url)
    if parsed_target is None:
        return None
    designer_name, design_id = parsed_target

    designers_payload = _fetch_json(
        f"{_API_BASE}/designers", timeout=timeout, max_bytes=_DESIGNERS_MAX_BYTES
    )
    if designers_payload is None:
        return None

    sub = _find_designer_sub(designers_payload, designer_name)
    if sub is None:
        log.info(
            "scrape_prinnit: no designer named %r found",
            sanitize_for_log(designer_name),
        )
        return None

    designs_payload = _fetch_json(
        f"{_API_BASE}/designs/{sub}", timeout=timeout, max_bytes=_DESIGNS_MAX_BYTES
    )
    if designs_payload is None:
        return None

    design = _find_design(designs_payload, design_id)
    if design is None:
        log.info(
            "scrape_prinnit: designId %r not found for designer %r",
            sanitize_for_log(design_id), sanitize_for_log(designer_name),
        )
        return None

    result = ScrapeResult(url=url, domain="prinnit.com")

    title = design.get("title")
    result.title = title.strip() if isinstance(title, str) and title.strip() else None

    raw_description = design.get("description")
    # prinnit's description is HTML; flatten to plain text since the frontend
    # renders session.description as a plain-text node (see docs/decisions.md).
    description = _html_to_text(raw_description) if isinstance(raw_description, str) else ""
    print_details = _build_print_details_block(design)
    if print_details:
        result.description = (
            f"{description}\n\n{print_details}" if description else print_details
        )
    else:
        result.description = description or None

    tags = design.get("tags")
    if isinstance(tags, list):
        result.raw_tags = [str(t).strip() for t in tags if str(t).strip()][:50]

    result.creator_name = designer_name
    result.creator_profile_url = f"https://prinnit.com/{designer_name}"
    result.source_site = "prinnit.com"
    # No license field on the design object — leave unset.
    result.license = None

    result.image_urls = _extract_image_urls(design, max_images)

    log.debug(
        "scrape_prinnit: %s -> title=%r images=%d tags=%d",
        sanitize_for_log(url), result.title, len(result.image_urls), len(result.raw_tags),
    )
    return result
