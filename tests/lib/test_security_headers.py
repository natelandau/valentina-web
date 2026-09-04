"""Tests for security headers via Flask-Talisman."""

from collections.abc import Iterator

import pytest
from flask import Flask
from loguru import logger

from vweb.lib.security import configure_security


@pytest.fixture
def loguru_warnings() -> Iterator[list[str]]:
    """Capture loguru warning messages emitted during a test."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    yield messages
    logger.remove(handler_id)


class TestSecurityHeaders:
    """Validate security headers are set on responses."""

    def test_x_content_type_options_is_set(self, client) -> None:
        """Verify X-Content-Type-Options nosniff header is present."""
        response = client.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_is_set(self, client) -> None:
        """Verify X-Frame-Options header is present."""
        assert client.get("/").headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_csp_allows_cdn_scripts(self, client) -> None:
        """Verify CSP script-src includes required CDN origins."""
        response = client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        assert "unpkg.com" in csp
        assert "kit.fontawesome.com" in csp


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
        assert "force_https is enabled" in loguru_warnings[0]
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
