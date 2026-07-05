"""Security Fix Set 1 — guarded_fetch (SSRF-hardened outbound fetch) tests.

Covers the four attack vectors closed by app.storage.ssrf_guard.guarded_fetch:
  1. Non-http(s) scheme is rejected before any socket is opened.
  2. A host resolving to a restricted IP range is rejected.
  3. A 3xx redirect to a blocked internal target is re-validated and refused
     (NOT auto-followed).
  4. An over-large response body aborts once the byte cap is exceeded.

Plus content-type enforcement and a happy-path fetch.

All tests are hermetic: DNS (socket.getaddrinfo) is mocked and HTTP is served by
an httpx.MockTransport — no real network calls are made.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import httpx
import pytest

from app.storage.ssrf_guard import (
    GuardedFetchError,
    GuardedResponse,
    SSRFBlockedError,
    guarded_fetch,
)

# ---------------------------------------------------------------------------
# DNS helpers
# ---------------------------------------------------------------------------

_PUBLIC_IP = "93.184.216.34"  # example.com — routable/public


def _fake_getaddrinfo_map(host, port, *a, **kw):  # type: ignore[no-untyped-def]
    """Resolve literal IPs to themselves; every hostname to a public IP.

    Lets a redirect target like ``http://10.0.0.5/`` resolve to a blocked
    address while the initial public host resolves clean.
    """
    try:
        # If host is already an IP literal, "resolve" it to itself.
        socket.inet_aton(host)
        resolved = host
    except OSError:
        resolved = _PUBLIC_IP
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved, port or 0))]


def _mock_transport(handler) -> httpx.MockTransport:  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# 1. Scheme rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/",
        "data:text/plain;base64,AAAA",
    ],
)
def test_rejects_non_http_scheme(url: str) -> None:
    """Disallowed schemes raise before any network activity."""
    called = {"hit": False}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        called["hit"] = True
        return httpx.Response(200)

    with pytest.raises(SSRFBlockedError, match="not allowed"):
        guarded_fetch(url, max_bytes=1024, transport=_mock_transport(handler))
    assert called["hit"] is False


# ---------------------------------------------------------------------------
# 2. IP-blocked host
# ---------------------------------------------------------------------------


def test_rejects_host_resolving_to_private_ip() -> None:
    """A host resolving to RFC-1918 is refused before connecting."""

    def fake(host, port, *a, **kw):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        return httpx.Response(200)

    with patch("socket.getaddrinfo", fake):
        with pytest.raises(SSRFBlockedError, match="restricted IP"):
            guarded_fetch(
                "http://internal.corp/x",
                max_bytes=1024,
                transport=_mock_transport(handler),
            )


def test_rejects_host_resolving_to_imds() -> None:
    """The cloud metadata endpoint is refused."""

    def fake(host, port, *a, **kw):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        return httpx.Response(200)

    with patch("socket.getaddrinfo", fake):
        with pytest.raises(SSRFBlockedError, match="restricted IP"):
            guarded_fetch(
                "http://metadata.internal/latest/meta-data/",
                max_bytes=1024,
                transport=_mock_transport(handler),
            )


# ---------------------------------------------------------------------------
# 3. Redirect to a blocked internal target is NOT followed
# ---------------------------------------------------------------------------


def test_redirect_to_internal_is_refused() -> None:
    """A 302 → internal target re-validates and raises (never fetches it)."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        # First (public) hop 302s to an internal address.
        return httpx.Response(302, headers={"location": "http://10.0.0.5/secret"})

    with patch("socket.getaddrinfo", _fake_getaddrinfo_map):
        with pytest.raises(SSRFBlockedError, match="restricted IP"):
            guarded_fetch(
                "http://public.example/start",
                max_bytes=1024,
                transport=_mock_transport(handler),
            )

    # Only the first (public) hop was ever requested; the internal target was
    # blocked at validation, before any request to 10.0.0.5.
    assert seen == ["http://public.example/start"]


def test_redirect_to_public_is_followed() -> None:
    """A redirect to another public host is validated and followed."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(
                302, headers={"location": "http://public.example/final"}
            )
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    with patch("socket.getaddrinfo", _fake_getaddrinfo_map):
        resp = guarded_fetch(
            "http://public.example/start",
            max_bytes=1024,
            transport=_mock_transport(handler),
        )

    assert isinstance(resp, GuardedResponse)
    assert resp.status_code == 200
    assert resp.text == "ok"
    assert resp.final_url == "http://public.example/final"
    assert len(seen) == 2


def test_redirect_hop_cap_enforced() -> None:
    """An endless redirect loop stops at the hop cap with GuardedFetchError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://public.example/again"})

    with patch("socket.getaddrinfo", _fake_getaddrinfo_map):
        with pytest.raises(GuardedFetchError, match="[Tt]oo many redirects"):
            guarded_fetch(
                "http://public.example/loop",
                max_bytes=1024,
                max_redirects=3,
                transport=_mock_transport(handler),
            )


# ---------------------------------------------------------------------------
# 4. Size cap
# ---------------------------------------------------------------------------


def test_size_cap_aborts_large_body() -> None:
    """A body larger than max_bytes raises GuardedFetchError."""
    big = b"x" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big, headers={"content-type": "image/png"})

    with patch("socket.getaddrinfo", _fake_getaddrinfo_map):
        with pytest.raises(GuardedFetchError, match="exceeded"):
            guarded_fetch(
                "http://public.example/big.png",
                max_bytes=1024,
                transport=_mock_transport(handler),
            )


def test_body_under_cap_is_returned() -> None:
    """A body within the cap is returned intact."""
    payload = b"y" * 500

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=payload, headers={"content-type": "image/png"}
        )

    with patch("socket.getaddrinfo", _fake_getaddrinfo_map):
        resp = guarded_fetch(
            "http://public.example/small.png",
            max_bytes=1024,
            allowed_content_types=("image/",),
            transport=_mock_transport(handler),
        )

    assert resp.content == payload
    assert resp.content_type == "image/png"


# ---------------------------------------------------------------------------
# 5. Content-type enforcement
# ---------------------------------------------------------------------------


def test_content_type_mismatch_rejected() -> None:
    """allowed_content_types=('image/',) rejects an HTML body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html></html>", headers={"content-type": "text/html"}
        )

    with patch("socket.getaddrinfo", _fake_getaddrinfo_map):
        with pytest.raises(GuardedFetchError, match="content-type"):
            guarded_fetch(
                "http://public.example/notanimage",
                max_bytes=1024,
                allowed_content_types=("image/",),
                transport=_mock_transport(handler),
            )
