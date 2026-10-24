"""The client's IP address, for audit entries and rate limiting.

``X-Forwarded-For`` is used only when the immediate sender (REMOTE_ADDR) is in
settings.TRUSTED_PROXIES. The chain is then read from the right, skipping trusted proxies; the
first untrusted address is the client. Anything malformed falls back to REMOTE_ADDR.

Measured on 2026-10-24: the Next.js rewrite proxy does NOT append the client address and
passes a client-supplied X-Forwarded-For through unchanged. Trusting the Next.js container
directly would therefore let any client choose its IP. Only trust proxies that append the
real client address, and only when clients cannot reach the backend or Next.js around them
(see docs/SECURITY.md, "Client IP addresses").
"""

import ipaddress

from django.conf import settings

MAX_FORWARDED_HEADER_LENGTH = 1024
MAX_FORWARDED_HOPS = 10

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _parse(value: str | None) -> IPAddress | None:
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _is_trusted(address: IPAddress) -> bool:
    return any(address in network for network in settings.TRUSTED_PROXIES)


def client_ip(request) -> str | None:
    if request is None:
        return None
    remote = _parse(request.META.get("REMOTE_ADDR"))
    if remote is None:
        return None
    if not _is_trusted(remote):
        return str(remote)

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not forwarded or len(forwarded) > MAX_FORWARDED_HEADER_LENGTH:
        return str(remote)
    hops = [hop for hop in forwarded.split(",")][-MAX_FORWARDED_HOPS:]
    for hop in reversed(hops):
        address = _parse(hop)
        if address is None:
            return str(remote)
        if not _is_trusted(address):
            return str(address)
    return str(remote)
