import ipaddress

import pytest
from django.test import RequestFactory

from apps.core.client_ip import client_ip

NEXTJS_CONTAINER = "172.18.0.5"
EDGE_PROXY = "10.0.0.2"


@pytest.fixture
def trust(settings):
    def _trust(*cidrs):
        settings.TRUSTED_PROXIES = [ipaddress.ip_network(c) for c in cidrs]

    _trust()  # default: trust nobody
    return _trust


def _request(remote_addr, forwarded=None):
    extra = {"REMOTE_ADDR": remote_addr}
    if forwarded is not None:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    return RequestFactory().get("/", **extra)


def test_without_trusted_proxies_forwarded_headers_are_ignored(trust):
    """Measured Next.js behaviour: it forwards a client-chosen X-Forwarded-For unchanged."""
    request = _request(NEXTJS_CONTAINER, forwarded="6.6.6.6")

    assert client_ip(request) == NEXTJS_CONTAINER


def test_untrusted_sender_cannot_choose_its_address(trust):
    trust("10.0.0.0/24")

    assert client_ip(_request("203.0.113.9", forwarded="6.6.6.6")) == "203.0.113.9"


def test_trusted_proxy_reports_the_client(trust):
    trust("10.0.0.0/24")

    assert client_ip(_request(EDGE_PROXY, forwarded="203.0.113.9")) == "203.0.113.9"


def test_spoofed_entries_left_of_the_real_client_are_ignored(trust):
    """A client sends 'X-Forwarded-For: 6.6.6.6'; the edge proxy appends the real address."""
    trust("10.0.0.0/24")

    request = _request(EDGE_PROXY, forwarded="6.6.6.6, 203.0.113.9")

    assert client_ip(request) == "203.0.113.9"


def test_chain_of_trusted_proxies_is_skipped(trust):
    trust("10.0.0.0/24", "172.18.0.0/16")

    request = _request(NEXTJS_CONTAINER, forwarded="6.6.6.6, 203.0.113.9, 10.0.0.2")

    assert client_ip(request) == "203.0.113.9"


@pytest.mark.parametrize(
    "forwarded",
    ["", "not-an-ip", "203.0.113.9, garbage", "203.0.113.9," * 200],
)
def test_malformed_or_oversized_headers_fall_back_to_the_sender(trust, forwarded):
    trust("10.0.0.0/24")

    assert client_ip(_request(EDGE_PROXY, forwarded=forwarded)) == EDGE_PROXY


def test_only_trusted_addresses_in_the_chain_returns_the_sender(trust):
    trust("10.0.0.0/24")

    assert client_ip(_request(EDGE_PROXY, forwarded="10.0.0.7")) == EDGE_PROXY


def test_ipv6_is_supported(trust):
    trust("fd00::/8")

    assert client_ip(_request("fd00::1", forwarded="2001:db8::5")) == "2001:db8::5"


def test_missing_or_invalid_remote_address(trust):
    assert client_ip(_request("")) is None
    assert client_ip(_request("unknown")) is None
    assert client_ip(None) is None
