"""Tests for the session cookie name set in the application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vweb.app import create_app
from vweb.config import RedisSettings

if TYPE_CHECKING:
    from vweb.config import Settings


def test_development_session_cookie_includes_port(test_settings: Settings) -> None:
    """Verify each development port gets its own session cookie."""
    # Given development settings on a worktree port
    settings = test_settings.model_copy(update={"port": 8091})

    # When the app is built
    app = create_app(settings_override=settings)

    # Then the session cookie is named after the port
    assert app.config["SESSION_COOKIE_NAME"] == "session_8091"


def test_production_session_cookie_keeps_default_name(test_settings: Settings) -> None:
    """Verify production keeps Flask's default session cookie name."""
    # Given production settings with Redis configured; the client connects lazily, so none is made
    settings = test_settings.model_copy(
        update={
            "env": "production",
            "force_https": False,
            "redis": RedisSettings(url="redis://127.0.0.1:6380/0"),
        }
    )

    # When the app is built
    app = create_app(settings_override=settings)

    # Then the session cookie keeps the default name
    assert app.config["SESSION_COOKIE_NAME"] == "session"


def test_https_production_session_cookie_uses_host_prefix(test_settings: Settings) -> None:
    """Verify HTTPS production names the cookie with the __Host- prefix."""
    # Given production settings served over HTTPS
    settings = test_settings.model_copy(
        update={
            "env": "production",
            "force_https": True,
            "redis": RedisSettings(url="redis://127.0.0.1:6380/0"),
        }
    )

    # When the app is built
    app = create_app(settings_override=settings)

    # Then browsers only accept the cookie as Secure, host-only, and Path=/
    assert app.config["SESSION_COOKIE_NAME"] == "__Host-session"
    assert app.config.get("SESSION_COOKIE_DOMAIN") in (None, False)
    assert app.config["SESSION_COOKIE_PATH"] in (None, "/")
