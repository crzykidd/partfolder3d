"""Scheme validation/normalization for user-facing URLs rendered as anchor hrefs.

Distinct from :mod:`app.storage.ssrf_guard` — that module controls *outbound
fetches* (blocks internal IPs, IMDS, redirects).  This module guards the *stored
value* that later becomes an ``<a href>`` in the UI, including the
**unauthenticated** public share page.

Only ``http://`` and ``https://`` URLs with a network host are permitted.
``javascript:``, ``data:``, ``vbscript:``, ``file:``, blank-with-scheme, and
scheme-relative ``//evil`` are rejected — React does not block a ``javascript:``
href, and the CSRF cookie is JS-readable, so one click on such a link is a full
authenticated request forgery.

Two entry points share one check:

* :func:`normalize_link_url` — returns ``None`` for an unsafe value (drop-and-log
  on scraper/ingestion paths, so a hostile page can't break an import).
* :func:`validate_link_url` — raises ``ValueError`` for an unsafe value, for use
  in a Pydantic field validator so the API boundary returns HTTP 422.

Both treat ``None``/empty/whitespace as an unset optional field (→ ``None``).
"""

from __future__ import annotations

from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def is_safe_link_url(value: str) -> bool:
    """Return ``True`` only for an ``http(s)://`` URL with a network host."""
    try:
        parsed = urlparse(value.strip())
    except (ValueError, AttributeError):
        return False
    return parsed.scheme in _ALLOWED_SCHEMES and bool(parsed.netloc)


def normalize_link_url(value: str | None) -> str | None:
    """Return the trimmed URL if safe, else ``None``.

    For scraper / ingestion paths: an unsafe or malformed value is silently
    dropped (caller should log a sanitized note) rather than stored.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped if is_safe_link_url(stripped) else None


def validate_link_url(value: str | None) -> str | None:
    """Pydantic field-validator helper for user-set URL fields.

    Empty/``None``/whitespace → ``None`` (these fields are optional).  A
    non-empty value that is not a safe ``http(s)`` URL raises ``ValueError`` so
    FastAPI returns a 422 with a clear message.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if not is_safe_link_url(stripped):
        raise ValueError("URL must be an http:// or https:// address")
    return stripped
