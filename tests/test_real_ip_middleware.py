"""Tests for the reverse-proxy header handling in _RealIPMiddleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vweb.app import _RealIPMiddleware

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


def _call(headers: dict[str, str], *, depth: int = 1) -> dict:
    """Run the middleware over a request with ``headers`` and return the environ it passes on."""
    seen: dict = {}

    def inner(environ: dict, start_response) -> Iterable[bytes]:
        seen.update(environ)
        start_response("200 OK", [])
        return [b""]

    environ = {
        "REMOTE_ADDR": "10.0.0.1",
        "HTTP_HOST": "valentina-noir.com",
        "wsgi.url_scheme": "http",
        **headers,
    }

    def start_response(*_: object) -> Callable[[bytes], object]:
        return lambda _data: None

    _RealIPMiddleware(inner, trusted_proxy_depth=depth)(environ, start_response)
    return seen


def test_client_forwarded_host_is_ignored() -> None:
    """Verify a client-supplied X-Forwarded-Host cannot change the host Flask builds URLs from."""
    # When a client sends its own X-Forwarded-Host
    environ = _call({"HTTP_X_FORWARDED_HOST": "evil.example"})

    # Then the real Host header is kept
    assert environ["HTTP_HOST"] == "valentina-noir.com"


@pytest.mark.parametrize(
    ("proto", "depth"),
    [
        # A client prepends a value and the trusted proxy appends the real scheme
        pytest.param("http, https", 1, id="proxy-appended-value-wins"),
        # The nearest proxy overwrites the header, so force_https must not redirect forever
        pytest.param("https", 2, id="single-value-at-any-depth"),
    ],
)
def test_forwarded_proto_sets_scheme(proto: str, depth: int) -> None:
    """Verify the scheme comes from the rightmost X-Forwarded-Proto entry."""
    assert _call({"HTTP_X_FORWARDED_PROTO": proto}, depth=depth)["wsgi.url_scheme"] == "https"


@pytest.mark.parametrize(
    ("headers", "depth", "expected"),
    [
        # A client spoofs a leading entry ahead of the real chain
        pytest.param(
            {"HTTP_X_FORWARDED_FOR": "6.6.6.6, 203.0.113.9, 172.16.0.2"},
            1,
            "203.0.113.9",
            id="xff-skips-trusted-proxy",
        ),
        pytest.param(
            {"HTTP_CF_CONNECTING_IP": " 198.51.100.7 ", "HTTP_X_FORWARDED_FOR": "6.6.6.6, 1.1.1.1"},
            1,
            "198.51.100.7",
            id="cloudflare-header-wins",
        ),
        pytest.param(
            {"HTTP_X_FORWARDED_FOR": "172.16.0.2"}, 1, "10.0.0.1", id="xff-shorter-than-depth"
        ),
        pytest.param({}, 1, "10.0.0.1", id="no-proxy-headers"),
    ],
)
def test_client_ip_resolution(headers: dict[str, str], depth: int, expected: str) -> None:
    """Verify which address becomes REMOTE_ADDR for each set of proxy headers."""
    assert _call(headers, depth=depth)["REMOTE_ADDR"] == expected
