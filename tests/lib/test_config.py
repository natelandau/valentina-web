"""Tests for application configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import vweb.config
from vweb.config import APISettings, RedisSettings, Settings, get_settings

if TYPE_CHECKING:
    from pathlib import Path

_API = APISettings(base_url="http://localhost:8080", api_key="test-api-key")
_REDIS_URL = "redis://localhost:6379/0"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param(
            {"env": "development", "redis": RedisSettings(url="")}, None, id="dev-no-redis"
        ),
        pytest.param(
            {"env": "production", "secret_key": "s3cret", "redis": RedisSettings(url=_REDIS_URL)},
            None,
            id="prod-with-redis",
        ),
        pytest.param(
            {"env": "production", "secret_key": "s3cret", "redis": RedisSettings(url="")},
            r"redis\.url.*required.*production",
            id="prod-no-redis",
        ),
        pytest.param(
            {"env": "production", "redis": RedisSettings(url=_REDIS_URL)},
            r"secret_key.*default.*production",
            id="prod-default-secret",
        ),
    ],
)
def test_settings_validation(overrides: dict, error: str | None) -> None:
    """Verify production fails fast without Redis or with the default secret key."""
    if error is None:
        Settings(_env_file=None, api=_API, **overrides)
    else:
        with pytest.raises(ValueError, match=error):
            Settings(_env_file=None, api=_API, **overrides)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        pytest.param({}, True, id="default-env-is-production"),
        pytest.param({"env": "production"}, True, id="production"),
        pytest.param({"env": "development"}, False, id="development"),
        pytest.param({"env": "production", "force_https": False}, False, id="prod-opt-out"),
    ],
)
def test_force_https_default(overrides: dict, expected: bool) -> None:  # noqa: FBT001
    """Verify HTTPS is enforced in production unless explicitly turned off."""
    settings = Settings(
        _env_file=None,
        api=_API,
        secret_key="s3cret",
        redis=RedisSettings(url=_REDIS_URL),
        **overrides,
    )

    assert settings.force_https is expected


def test_get_settings_returns_one_shared_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify settings load once from the environment and are reused."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vweb.config, "_settings", None)
    monkeypatch.setenv("VWEB_ENV", "development")
    monkeypatch.setenv("VWEB_API__BASE_URL", "http://api.example")
    monkeypatch.setenv("VWEB_API__API_KEY", "k")

    first = get_settings()

    assert first.api.base_url == "http://api.example"
    assert get_settings() is first


def test_create_app_passes_api_settings_to_vclient() -> None:
    """Verify create_app configures the API client with the retry and pool settings."""
    from vweb.app import create_app

    settings = Settings(
        _env_file=None,
        env="development",
        secret_key="test-secret-key",
        redis=RedisSettings(url=""),
        api=APISettings(
            base_url="http://localhost:8080",
            api_key="test-api-key",
            max_retries=1,
            retry_delay=0.25,
            max_retry_delay=1.0,
            retry_budget=4.0,
            max_parallel_requests=2,
        ),
    )

    app = create_app(settings_override=settings)

    config = app.extensions["vclient"]._config
    assert config.max_retries == 1
    assert config.retry_delay == 0.25
    assert config.max_retry_delay == 1.0
    assert config.retry_budget == 4.0
    assert config.max_parallel_requests == 2
