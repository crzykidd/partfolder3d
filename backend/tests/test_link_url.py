"""Unit tests for app.storage.link_url — scheme guard for URLs rendered as hrefs.

Covers the shared validator used by the API schema boundary (raises → 422) and
the scraper/ingestion drop-to-None path.  See audit-2026-07-03 §A [med].
"""
from __future__ import annotations

import pytest

from app.storage.link_url import (
    is_safe_link_url,
    normalize_link_url,
    validate_link_url,
)

_SAFE = [
    "http://example.com",
    "https://printables.com/model/123",
    "https://makerworld.com/en/@designer",
    "  https://example.com/x  ",  # surrounding whitespace tolerated
]

_UNSAFE = [
    "javascript:alert(1)",
    "javascript:void(0)",
    "JavaScript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "ftp://example.com/f",
    "//evil.example.com",  # scheme-relative
    "not-a-url",
    "mailto:a@b.com",
]


@pytest.mark.parametrize("url", _SAFE)
def test_is_safe_link_url_allows_http(url: str) -> None:
    assert is_safe_link_url(url) is True


@pytest.mark.parametrize("url", _UNSAFE)
def test_is_safe_link_url_rejects_dangerous(url: str) -> None:
    assert is_safe_link_url(url) is False


def test_normalize_returns_none_for_empty_and_unsafe() -> None:
    assert normalize_link_url(None) is None
    assert normalize_link_url("") is None
    assert normalize_link_url("   ") is None
    assert normalize_link_url("javascript:alert(1)") is None
    # scraper path drops silently rather than raising
    assert normalize_link_url("data:text/html,x") is None


def test_normalize_trims_and_keeps_safe() -> None:
    assert normalize_link_url("  https://example.com/x  ") == "https://example.com/x"


def test_validate_returns_none_for_empty() -> None:
    # optional/nullable fields must survive validation
    assert validate_link_url(None) is None
    assert validate_link_url("") is None
    assert validate_link_url("   ") is None


def test_validate_raises_for_dangerous() -> None:
    with pytest.raises(ValueError, match="http"):
        validate_link_url("javascript:alert(1)")


def test_validate_keeps_and_trims_safe() -> None:
    assert validate_link_url("  https://example.com/x  ") == "https://example.com/x"
