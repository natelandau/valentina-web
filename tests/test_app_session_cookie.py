"""Tests for the session cookie name set in the application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vweb.app import create_app
from vweb.config import RedisSettings

if TYPE_CHECKING:
    from vweb.config import Settings


@pytest.mark.parametrize(
    ("env", "force_https", "expected"),
    [
        # Browsers share cookies across ports, so each dev checkout needs its own name
        pytest.param("development", False, "session_8091", id="dev-per-port"),
        pytest.param("production", False, "session", id="prod-http"),
        # Browsers accept __Host- cookies only when Secure, host-only, and Path=/
        pytest.param("production", True, "__Host-session", id="prod-https"),
    ],
)
def test_session_cookie_name(
    test_settings: Settings,
    env: str,
    force_https: bool,  # noqa: FBT001
    expected: str,
) -> None:
    """Verify the session cookie name per environment, and host-only scoping under HTTPS."""
    # The Redis client connects lazily, so building the app opens no connection
    settings = test_settings.model_copy(
        update={
            "env": env,
            "port": 8091,
            "force_https": force_https,
            "redis": RedisSettings(url="redis://127.0.0.1:6380/0" if env == "production" else ""),
        }
    )

    app = create_app(settings_override=settings)

    assert app.config["SESSION_COOKIE_NAME"] == expected
    assert app.config.get("SESSION_COOKIE_DOMAIN") in {None, False}
    assert app.config["SESSION_COOKIE_PATH"] in {None, "/"}
