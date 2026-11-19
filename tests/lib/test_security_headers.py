"""Tests for security headers and cookie flags set via Flask-Talisman."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flask import Flask, session
from loguru import logger

from vweb.app import create_app
from vweb.config import RedisSettings
from vweb.lib.security import configure_security

if TYPE_CHECKING:
    from collections.abc import Iterator

    from vweb.config import Settings


@pytest.fixture
def loguru_warnings() -> Iterator[list[str]]:
    """Capture loguru warning messages emitted during a test."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    yield messages
    logger.remove(handler_id)


@pytest.fixture
def https_app(test_settings: Settings) -> Flask:
    """Build a production app that enforces HTTPS.

    model_copy skips validation, so the app runs without Redis and opens no connection.
    """
    settings = test_settings.model_copy(
        update={"env": "production", "force_https": True, "redis": RedisSettings(url="")}
    )
    return create_app(settings_override=settings)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "SAMEORIGIN"),
    ],
)
def test_security_header(client, header: str, expected: str) -> None:
    """Verify each response carries the anti-sniffing and anti-framing headers."""
    assert client.get("/").headers.get(header) == expected


def test_csp_restricts_sources_and_allows_cdns(client) -> None:
    """Verify the CSP defaults to same-origin and admits the CDNs the pages load scripts from."""
    csp = client.get("/").headers.get("Content-Security-Policy", "")

    assert "default-src 'self'" in csp
    for origin in ("unpkg.com", "cdn.jsdelivr.net", "kit.fontawesome.com"):
        assert origin in csp


def test_https_app_redirects_plain_http(https_app: Flask) -> None:
    """Verify a plain HTTP request is redirected to HTTPS."""
    response = https_app.test_client().get("/", base_url="http://vweb.test")

    assert response.status_code in {301, 302}
    assert response.headers["Location"].startswith("https://vweb.test/")


def test_https_app_sends_hsts(https_app: Flask) -> None:
    """Verify HTTPS responses tell browsers to stay on HTTPS."""
    response = https_app.test_client().get("/", base_url="https://vweb.test")

    assert "max-age=" in response.headers.get("Strict-Transport-Security", "")


@pytest.mark.parametrize(
    ("force_https", "base_url", "expected_flags", "absent_flags"),
    [
        (True, "https://vweb.test", {"httponly", "secure", "samesite=none"}, set()),
        (False, "http://vweb.test", {"httponly", "samesite=lax"}, {"secure"}),
    ],
)
def test_session_cookie_flags(
    test_settings: Settings,
    force_https: bool,  # noqa: FBT001
    base_url: str,
    expected_flags: set[str],
    absent_flags: set[str],
) -> None:
    """Verify the session cookie is HttpOnly, and Secure with SameSite=None only over HTTPS.

    Sign in with Apple posts back cross-site, which needs SameSite=None, which needs Secure.
    """
    settings = test_settings.model_copy(
        update={"env": "production", "force_https": force_https, "redis": RedisSettings(url="")}
    )
    app = create_app(settings_override=settings)

    def _write_session() -> str:
        session["probe"] = "1"
        return ""

    # /auth/ paths skip the login redirect, so the probe reaches the session
    app.add_url_rule("/auth/__session_probe", view_func=_write_session)

    response = app.test_client().get("/auth/__session_probe", base_url=base_url)

    flags = {part.strip().lower() for part in response.headers["Set-Cookie"].split(";")[1:]}
    assert expected_flags <= flags
    assert not absent_flags & flags


class TestForceHttpsLoopbackWarning:
    """Validate the startup warning for force_https on a loopback bind address."""

    @pytest.mark.parametrize(
        "host", ["127.0.0.1", "127.0.1.1", "localhost", "Localhost", "::1", "[::1]"]
    )
    def test_warns_for_loopback_host(self, test_settings, loguru_warnings, host) -> None:
        """Verify every loopback spelling triggers the warning."""
        settings = test_settings.model_copy(update={"force_https": True, "host": host})
        configure_security(Flask("test"), settings)
        assert len(loguru_warnings) == 1
        assert f"https://{host}:{settings.port}" in loguru_warnings[0]

    @pytest.mark.parametrize(
        ("force_https", "host"),
        [(False, "127.0.0.1"), (True, "0.0.0.0"), (True, "example.com")],  # noqa: S104
    )
    def test_silent_otherwise(self, test_settings, loguru_warnings, force_https, host) -> None:
        """Verify no warning when HTTPS is off or the bind address is not loopback."""
        settings = test_settings.model_copy(update={"force_https": force_https, "host": host})
        configure_security(Flask("test"), settings)
        assert loguru_warnings == []
