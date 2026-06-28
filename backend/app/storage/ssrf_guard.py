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
from urllib.parse import urlparse

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
    """Raised when a URL is blocked by the SSRF guard."""


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

    for _fam, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        if _is_blocked_ip(ip_str):
            log.warning(
                "ssrf_guard: blocked URL %s — resolved to %s which is in a restricted range",
                url, ip_str,
            )
            raise SSRFBlockedError(
                f"URL {url!r} resolves to {ip_str!r}, which is in a restricted IP range "
                "and cannot be fetched by this server."
            )

    log.debug("ssrf_guard: URL %s passed (hosts=%s)", url, [s[4][0] for s in addr_infos])
