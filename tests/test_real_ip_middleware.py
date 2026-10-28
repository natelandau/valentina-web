"""Tests for the reverse-proxy header handling in _RealIPMiddleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vweb.app import _RealIPMiddleware

if TYPE_CHECKING:
    from collections.abc import Iterable


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
    _RealIPMiddleware(inner, trusted_proxy_depth=depth)(environ, lambda *_: None)
    return seen


def test_client_forwarded_host_is_ignored() -> None:
    """Verify a client-supplied X-Forwarded-Host cannot change the host Flask builds URLs from."""
    # When a client sends its own X-Forwarded-Host
    environ = _call({"HTTP_X_FORWARDED_HOST": "evil.example"})

    # Then the real Host header is kept
    assert environ["HTTP_HOST"] == "valentina-noir.com"


def test_forwarded_proto_uses_value_appended_by_trusted_proxy() -> None:
    """Verify the scheme comes from the trusted proxy's entry, not a client-prepended one."""
    # When a client prepends a value and the trusted proxy appends the real scheme
    environ = _call({"HTTP_X_FORWARDED_PROTO": "http, https"})

    # Then the proxy's value wins
    assert environ["wsgi.url_scheme"] == "https"


def test_forwarded_proto_single_value_trusted_at_any_depth() -> None:
    """Verify an overwritten single-value header still sets the scheme behind several proxies."""
    # When the nearest proxy overwrites the header and two proxies are trusted
    environ = _call({"HTTP_X_FORWARDED_PROTO": "https"}, depth=2)

    # Then the scheme follows the proxy so force_https does not redirect forever
    assert environ["wsgi.url_scheme"] == "https"


def test_forwarded_for_skips_trusted_proxy_entries() -> None:
    """Verify the client IP is read from the right of X-Forwarded-For past trusted proxies."""
    # When a client spoofs a leading entry ahead of the real chain
    environ = _call({"HTTP_X_FORWARDED_FOR": "6.6.6.6, 203.0.113.9, 172.16.0.2"})

    # Then the entry just left of the trusted proxy is used
    assert environ["REMOTE_ADDR"] == "203.0.113.9"
