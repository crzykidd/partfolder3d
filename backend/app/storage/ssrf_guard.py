"""SSRF guard for outbound HTTP requests made by PartFolder 3D.

Both the URL scraper (Phase 5) and the instance-share-link importer (Phase 7)
fetch user-supplied URLs.  Without a guard they could be used to probe internal
services, cloud-metadata endpoints, or other resources on the host network.

Design
------
- Validate scheme is http or https.
- Resolve the hostname to all its IP addresses (A + AAAA records).
- Reject any address that falls in a non-routable / special-purpose range:
    * Loopback:          127.0.0.0/8  |  ::1
    * Link-local:        169.254.0.0/16  |  fe80::/10
    * Private (RFC 1918): 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
    * Unique-local (ULA): fc00::/7
    * Cloud metadata:    169.254.169.254 (AWS/GCP/Azure/DO/Azure IMDS)
                         fd00:ec2::254   (AWS IPv6 IMDS)
    * Multicast:         224.0.0.0/4  |  ff00::/8
    * Unspecified:       0.0.0.0/8  |  ::/128
    * Broadcast:         255.255.255.255/32

Usage::

    from app.storage.ssrf_guard import assert_safe_url, SSRFBlockedError

    try:
        assert_safe_url(url)
    except SSRFBlockedError as exc:
        # Treat as a user-supplied bad URL; surface the message.
        raise HTTPException(400, str(exc)) from exc

The guard raises SSRFBlockedError on any rejected URL.  Callers decide whether
to surface the reason to the user (generally fine — we are not leaking internal
topology by saying "that IP is not routable").

DNS resolution is synchronous (socket.getaddrinfo) which is acceptable for the
low-frequency import paths where this is called (never in hot loops).  The guard
runs *before* any outbound connection is opened.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Private / reserved networks to block
# ---------------------------------------------------------------------------

_BLOCKED_NETS_V4: list[ipaddress.IPv4Network] = [
    ipaddress.IPv4Network("0.0.0.0/8"),          # "This" network
    ipaddress.IPv4Network("10.0.0.0/8"),          # RFC 1918 private
    ipaddress.IPv4Network("100.64.0.0/10"),       # Carrier-grade NAT (RFC 6598)
    ipaddress.IPv4Network("127.0.0.0/8"),         # Loopback
    ipaddress.IPv4Network("169.254.0.0/16"),      # Link-local / cloud-metadata IMDS
    ipaddress.IPv4Network("172.16.0.0/12"),       # RFC 1918 private
    ipaddress.IPv4Network("192.0.0.0/24"),        # IETF Protocol Assignments
    ipaddress.IPv4Network("192.168.0.0/16"),      # RFC 1918 private
    ipaddress.IPv4Network("198.18.0.0/15"),       # Benchmark testing (RFC 2544)
    ipaddress.IPv4Network("198.51.100.0/24"),     # TEST-NET-2 (RFC 5737)
    ipaddress.IPv4Network("203.0.113.0/24"),      # TEST-NET-3 (RFC 5737)
    ipaddress.IPv4Network("224.0.0.0/4"),         # Multicast
    ipaddress.IPv4Network("240.0.0.0/4"),         # Reserved
    ipaddress.IPv4Network("255.255.255.255/32"),  # Broadcast
]

_BLOCKED_NETS_V6: list[ipaddress.IPv6Network] = [
    ipaddress.IPv6Network("::1/128"),             # Loopback
    ipaddress.IPv6Network("::/128"),              # Unspecified
    ipaddress.IPv6Network("::ffff:0:0/96"),       # IPv4-mapped (covers v4 blocked ranges via v6)
    ipaddress.IPv6Network("64:ff9b::/96"),        # IPv4/IPv6 translation (RFC 6052)
    ipaddress.IPv6Network("100::/64"),            # Discard prefix
    ipaddress.IPv6Network("fc00::/7"),            # Unique-local (ULA, RFC 4193) — private
    ipaddress.IPv6Network("fe80::/10"),           # Link-local
    ipaddress.IPv6Network("ff00::/8"),            # Multicast
    ipaddress.IPv6Network("fd00:ec2::/32"),       # AWS IPv6 IMDS (fd00:ec2::254)
]


def _is_blocked_ip(addr_str: str) -> bool:
    """Return True if the IP address string is in a blocked range."""
    try:
        ip = ipaddress.ip_address(addr_str)
    except ValueError:
        # Not a parseable IP — block it to be safe
        return True

    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in _BLOCKED_NETS_V4)
    # IPv6
    return any(ip in net for net in _BLOCKED_NETS_V6)


# ---------------------------------------------------------------------------
# Public exception and guard function
# ---------------------------------------------------------------------------


class SSRFBlockedError(ValueError):
    """Raised when a URL is blocked by the SSRF guard.

    Covers a disallowed scheme, a host resolving to a restricted IP range, a
    failed DNS resolution, or a redirect target that fails the same checks.
    """


class GuardedFetchError(Exception):
    """Raised by :func:`guarded_fetch` for non-SSRF failures.

    Distinct from SSRFBlockedError so callers can tell "blocked for safety"
    apart from "response too large / disallowed content-type / too many
    redirects".  Both are treated as a failed fetch by callers.
    """


def sanitize_for_log(value: str) -> str:
    """Escape CR/LF in a user-supplied string before it is logged.

    Prevents log-injection / forged log lines when an attacker-controlled URL,
    host, or title is interpolated into a log record.  Reuse this everywhere a
    scraped/user URL reaches ``log.*`` — do not re-implement the replace inline.
    """
    return value.replace("\r", "\\r").replace("\n", "\\n")


def assert_safe_url(url: str) -> None:
    """Validate *url* is safe to fetch externally.

    Raises SSRFBlockedError if:
    - The scheme is not http or https.
    - The hostname resolves to any private/reserved IP address.
    - DNS resolution fails (treated as blocked).

    Does not open a connection; purely DNS-based pre-flight check.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SSRFBlockedError(
            f"URL scheme {scheme!r} is not allowed; only http and https are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("URL has no hostname.")

    # Resolve hostname to all A/AAAA addresses
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"DNS resolution failed for {hostname!r}: {exc}") from exc

    if not addr_infos:
        raise SSRFBlockedError(f"No DNS records for hostname {hostname!r}.")

    # Sanitize URL for logging: strip CR/LF to prevent log injection.
    _safe_url = sanitize_for_log(url)

    for _fam, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        if _is_blocked_ip(ip_str):
            log.warning(
                "ssrf_guard: blocked URL %s — resolved to %s which is in a restricted range",
                _safe_url, ip_str,
            )
            raise SSRFBlockedError(
                f"URL {url!r} resolves to {ip_str!r}, which is in a restricted IP range "
                "and cannot be fetched by this server."
            )

    log.debug("ssrf_guard: URL %s passed (hosts=%s)", _safe_url, [s[4][0] for s in addr_infos])


# ---------------------------------------------------------------------------
# Guarded outbound fetch — the single chokepoint for user-influenced fetches
# ---------------------------------------------------------------------------

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

# Default UA used by outbound fetches that don't override it.
_DEFAULT_UA = "PartFolder3D/1 (+https://github.com/crzykidd/partfolder3d)"


@dataclass
class GuardedResponse:
    """The outcome of a successful :func:`guarded_fetch`.

    ``content`` holds the (capped) response body; ``text`` decodes it lazily.
    The full redirect chain has already been validated hop-by-hop.
    """

    status_code: int
    headers: dict[str, str]
    content: bytes
    final_url: str
    encoding: str = "utf-8"

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding, errors="replace")


def _charset_from_content_type(content_type: str) -> str:
    for part in content_type.split(";"):
        part = part.strip().lower()
        if part.startswith("charset="):
            enc = part.split("=", 1)[1].strip().strip('"').strip("'")
            if enc:
                return enc
    return "utf-8"


def guarded_fetch(
    url: str,
    *,
    max_bytes: int,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
    max_redirects: int = 5,
    allowed_content_types: tuple[str, ...] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> GuardedResponse:
    """Fetch *url* with full SSRF hardening.  The single outbound chokepoint.

    Guarantees, in order, on every hop (initial request AND each redirect):
      1. Scheme is http/https only (rejected before any socket is opened).
      2. The host resolves ONLY to routable public IPs (``assert_safe_url``).
    Redirects are NOT auto-followed by httpx (``follow_redirects=False``); each
    ``Location`` is re-validated through the full scheme+DNS+IP checks before
    the next hop, capped at *max_redirects* hops.  The body is streamed and the
    read is aborted the moment it exceeds *max_bytes* (never buffers unbounded).

    Args:
        max_bytes: hard cap on the response body; exceeding it raises
            GuardedFetchError before the whole body is materialized.
        allowed_content_types: if given, the final response's Content-Type must
            start with one of these prefixes (e.g. ``("image/",)``); otherwise
            GuardedFetchError is raised.

    Raises:
        SSRFBlockedError: bad scheme / restricted IP on any hop.
        GuardedFetchError: too many redirects, missing redirect target,
            disallowed content-type, or body over the cap.

    Note — DNS-rebinding (TOCTOU) residual: ``assert_safe_url`` resolves+checks
    the host, then httpx resolves again when it connects.  A hostile resolver
    could return a public IP to the pre-check and a private IP to httpx.  Full
    closure requires pinning the connection to the vetted IP (custom transport;
    complicated by HTTPS SNI/cert validation) and is deliberately NOT done here
    — the redirect + scheme + cap guards are the must-have.  Recorded as a
    residual in docs/decisions.md.
    """
    req_headers = {"User-Agent": _DEFAULT_UA}
    if headers:
        req_headers.update(headers)

    current_url = url
    with httpx.Client(
        timeout=timeout, follow_redirects=False, transport=transport
    ) as client:
        for _hop in range(max_redirects + 1):
            # Re-run the FULL scheme + DNS + IP validation on every hop.
            assert_safe_url(current_url)

            with client.stream("GET", current_url, headers=req_headers) as resp:
                if resp.status_code in _REDIRECT_CODES:
                    location = resp.headers.get("location")
                    if not location:
                        # A 3xx with no Location — nothing to follow; treat as final.
                        resp.read()
                        return _finalize(resp, current_url, max_bytes, allowed_content_types)
                    current_url = urljoin(current_url, location)
                    log.debug(
                        "guarded_fetch: redirect → %s", sanitize_for_log(current_url)
                    )
                    continue

                return _finalize(resp, current_url, max_bytes, allowed_content_types)

    raise GuardedFetchError(
        f"Too many redirects (>{max_redirects}) fetching {sanitize_for_log(url)}"
    )


def _finalize(
    resp: httpx.Response,
    final_url: str,
    max_bytes: int,
    allowed_content_types: tuple[str, ...] | None,
) -> GuardedResponse:
    """Enforce content-type + size cap while streaming, then build the result."""
    content_type = resp.headers.get("content-type", "")
    if allowed_content_types is not None:
        ct_main = content_type.split(";")[0].strip().lower()
        if not any(ct_main.startswith(p) for p in allowed_content_types):
            raise GuardedFetchError(
                f"Disallowed content-type {content_type!r} for "
                f"{sanitize_for_log(final_url)}"
            )

    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise GuardedFetchError(
                f"Response body exceeded {max_bytes} bytes fetching "
                f"{sanitize_for_log(final_url)}"
            )
        chunks.append(chunk)

    return GuardedResponse(
        status_code=resp.status_code,
        headers={k.lower(): v for k, v in resp.headers.items()},
        content=b"".join(chunks),
        final_url=final_url,
        encoding=_charset_from_content_type(content_type),
    )
