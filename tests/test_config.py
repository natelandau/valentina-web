"""Tests for application configuration."""

import pytest

from vweb.config import (
    APISettings,
    OAuthProviderSettings,
    OAuthSettings,
    RedisSettings,
    Settings,
)


class TestSettingsValidation:
    """Validate environment-specific configuration rules."""

    def test_development_env_without_redis_url_succeeds(self) -> None:
        """Verify development mode does not require a Redis URL."""
        settings = Settings(
            _env_file=None,
            env="development",
            redis=RedisSettings(),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
                default_company_id="test-company-id",
                server_admin_user_id="test-owner-id",
            ),
        )
        assert settings.env == "development"

    def test_production_env_without_redis_url_raises(self) -> None:
        """Verify production mode fails fast when redis.url is missing."""
        with pytest.raises(ValueError, match=r"redis\.url.*required.*production"):
            Settings(
                _env_file=None,
                env="production",
                secret_key="production-secret-key",  # noqa: S106
                redis=RedisSettings(url=""),
                api=APISettings(
                    base_url="http://localhost:8080",
                    api_key="test-api-key",
                    default_company_id="test-company-id",
                    server_admin_user_id="test-owner-id",
                ),
            )

    def test_production_env_with_redis_url_succeeds(self) -> None:
        """Verify production mode accepts a valid redis.url."""
        settings = Settings(
            _env_file=None,
            env="production",
            secret_key="production-secret-key",  # noqa: S106
            redis=RedisSettings(url="redis://localhost:6379/0"),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
                default_company_id="test-company-id",
                server_admin_user_id="test-owner-id",
            ),
        )
        assert settings.redis.url == "redis://localhost:6379/0"

    def test_default_env_is_production(self) -> None:
        """Verify the default environment is production."""
        settings = Settings(
            _env_file=None,
            secret_key="production-secret-key",  # noqa: S106
            redis=RedisSettings(),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
                default_company_id="test-company-id",
                server_admin_user_id="test-owner-id",
            ),
        )
        assert settings.env == "production"

    def test_production_env_with_default_secret_key_raises(self) -> None:
        """Verify production mode rejects the default secret key."""
        with pytest.raises(ValueError, match=r"secret_key.*default.*production"):
            Settings(
                _env_file=None,
                env="production",
                redis=RedisSettings(url="redis://localhost:6379/0"),
                secret_key="change-me-in-production",  # noqa: S106
                api=APISettings(
                    base_url="http://localhost:8080",
                    api_key="test-api-key",
                    default_company_id="test-company-id",
                    server_admin_user_id="test-owner-id",
                ),
            )

    def test_vclient_has_no_default_user_id(self) -> None:
        """Verify VClientSettings no longer includes default_user_id."""
        settings = APISettings(
            base_url="http://localhost:8080",
            api_key="test-api-key",
            default_company_id="test-company-id",
            server_admin_user_id="test-owner-id",
        )
        assert not hasattr(settings, "default_user_id")

    def test_oauth_settings_default_on_settings(self) -> None:
        """Verify Settings includes OAuthSettings with correct defaults."""
        settings = Settings(
            _env_file=None,
            secret_key="production-secret-key",  # noqa: S106
            redis=RedisSettings(),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
                default_company_id="test-company-id",
                server_admin_user_id="test-owner-id",
            ),
        )
        assert isinstance(settings.oauth, OAuthSettings)
        assert isinstance(settings.oauth.discord, OAuthProviderSettings)
        assert settings.oauth.discord.client_id == ""
        assert settings.oauth.discord.client_secret == ""

    def test_oauth_settings_accepts_custom_values(self) -> None:
        """Verify OAuthSettings accepts custom Discord credentials."""
        oauth = OAuthSettings(
            discord=OAuthProviderSettings(
                client_id="my-client-id",
                client_secret="my-client-secret",  # noqa: S106
            ),
        )
        assert oauth.discord.client_id == "my-client-id"
        assert oauth.discord.client_secret == "my-client-secret"  # noqa: S105
