"""Guards against the checker being used to reach internal networks (SSRF).

Link URLs come from KB articles, which are untrusted input once the app is
public. Every request (and every redirect hop) must resolve to a public IP.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

MAX_REDIRECTS = 10


class UnsafeURL(Exception):
    """Raised when a URL targets a non-public address or unsupported scheme."""


def assert_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL(f"Unsupported URL scheme: {parsed.scheme or 'none'}")
    host = parsed.hostname
    if not host:
        raise UnsafeURL("URL has no host.")

    try:
        infos = socket.getaddrinfo(host, parsed.port or 443)
    except socket.gaierror:
        # Unresolvable hosts are not a safety problem; let the normal request
        # path report them as broken links.
        return

    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            raise UnsafeURL(
                "Link points to a private or internal address and was not "
                "requested."
            )


def safe_get(url, *, timeout, verify, headers, follow_redirects=True):
    """requests.get that re-checks the destination on every redirect hop."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_url(current)
        response = requests.get(
            current, timeout=timeout, verify=verify, headers=headers,
            allow_redirects=False,
        )
        location = response.headers.get("Location")
        if follow_redirects and response.is_redirect and location:
            current = urljoin(current, location)
            continue
        return response
    raise requests.exceptions.TooManyRedirects(
        f"Exceeded {MAX_REDIRECTS} redirects."
    )
