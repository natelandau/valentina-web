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
            ),
        )
        assert settings.env == "development"

    def test_production_env_without_redis_url_raises(self) -> None:
        """Verify production mode fails fast when redis.url is missing."""
        with pytest.raises(ValueError, match=r"redis\.url.*required.*production"):
            Settings(
                _env_file=None,
                env="production",
                secret_key="production-secret-key",
                redis=RedisSettings(url=""),
                api=APISettings(
                    base_url="http://localhost:8080",
                    api_key="test-api-key",
                ),
            )

    def test_production_env_with_redis_url_succeeds(self) -> None:
        """Verify production mode accepts a valid redis.url."""
        settings = Settings(
            _env_file=None,
            env="production",
            secret_key="production-secret-key",
            redis=RedisSettings(url="redis://localhost:6379/0"),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
            ),
        )
        assert settings.redis.url == "redis://localhost:6379/0"

    def test_default_env_is_production(self) -> None:
        """Verify the default environment is production."""
        settings = Settings(
            _env_file=None,
            secret_key="production-secret-key",
            redis=RedisSettings(),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
            ),
        )
        assert settings.env == "production"

    def test_force_https_defaults_on_in_production(self) -> None:
        """Verify force_https defaults to True when env is production."""
        settings = Settings(
            _env_file=None,
            env="production",
            secret_key="production-secret-key",
            redis=RedisSettings(url="redis://localhost:6379/0"),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
            ),
        )
        assert settings.force_https is True

    def test_force_https_defaults_off_in_development(self) -> None:
        """Verify force_https defaults to False when env is development."""
        settings = Settings(
            _env_file=None,
            env="development",
            redis=RedisSettings(),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
            ),
        )
        assert settings.force_https is False

    def test_force_https_can_be_disabled_in_production(self) -> None:
        """Verify force_https can be explicitly disabled for local prod-mode runs."""
        settings = Settings(
            _env_file=None,
            env="production",
            force_https=False,
            secret_key="production-secret-key",
            redis=RedisSettings(url="redis://localhost:6379/0"),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
            ),
        )
        assert settings.force_https is False

    def test_production_env_with_default_secret_key_raises(self) -> None:
        """Verify production mode rejects the default secret key."""
        with pytest.raises(ValueError, match=r"secret_key.*default.*production"):
            Settings(
                _env_file=None,
                env="production",
                redis=RedisSettings(url="redis://localhost:6379/0"),
                secret_key="change-me-in-production",
                api=APISettings(
                    base_url="http://localhost:8080",
                    api_key="test-api-key",
                ),
            )

    def test_vclient_has_no_default_user_id(self) -> None:
        """Verify VClientSettings no longer includes default_user_id."""
        settings = APISettings(
            base_url="http://localhost:8080",
            api_key="test-api-key",
        )
        assert not hasattr(settings, "default_user_id")

    def test_oauth_settings_default_on_settings(self) -> None:
        """Verify Settings includes OAuthSettings with correct defaults."""
        settings = Settings(
            _env_file=None,
            secret_key="production-secret-key",
            redis=RedisSettings(),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
            ),
        )
        assert isinstance(settings.oauth, OAuthSettings)
        assert isinstance(settings.oauth.discord, OAuthProviderSettings)
        assert settings.oauth.discord.client_id == ""
        assert settings.oauth.discord.client_secret == ""

    def test_settings_without_company_fields(self) -> None:
        """Verify Settings constructs without default_company_id or server_admin_user_id."""
        s = Settings(
            _env_file=None,
            app_name="Test",
            env="development",
            secret_key="test",
            api=APISettings(
                base_url="http://localhost",
                api_key="test-key",
            ),
        )
        assert s.api.base_url == "http://localhost"
        assert not hasattr(s.api, "default_company_id")
        assert not hasattr(s.api, "server_admin_user_id")

    def test_oauth_settings_accepts_custom_values(self) -> None:
        """Verify OAuthSettings accepts custom Discord credentials."""
        oauth = OAuthSettings(
            discord=OAuthProviderSettings(
                client_id="my-client-id",
                client_secret="my-client-secret",
            ),
        )
        assert oauth.discord.client_id == "my-client-id"
        assert oauth.discord.client_secret == "my-client-secret"


class TestAPIRetrySettings:
    """Verify the API retry settings reach the API client."""

    def test_retry_defaults_fit_a_web_request(self) -> None:
        """Verify the retry defaults keep one API call short enough for a web request."""
        # Given/When: API settings with only the required fields
        api = APISettings(base_url="http://localhost:8080", api_key="test-api-key")

        # Then: Retries are few, short, and inside a 10 second budget
        assert api.max_retries == 2
        assert api.retry_delay == 0.5
        assert api.max_retry_delay == 2.0
        assert api.retry_budget == 10.0

    def test_create_app_passes_retry_settings_to_vclient(self) -> None:
        """Verify create_app configures the API client with every retry setting."""
        from vweb.app import create_app

        # Given: Settings with custom retry values
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
            ),
        )

        # When: Creating the app
        app = create_app(settings_override=settings)

        # Then: The API client carries the configured retry values
        config = app.extensions["vclient"]._config
        assert config.max_retries == 1
        assert config.retry_delay == 0.25
        assert config.max_retry_delay == 1.0
        assert config.retry_budget == 4.0

    def test_create_app_passes_max_parallel_requests_to_vclient(self) -> None:
        """Verify create_app sizes the API client's worker pool from settings."""
        from vweb.app import create_app

        # Given: Settings with a custom worker count
        settings = Settings(
            _env_file=None,
            env="development",
            secret_key="test-secret-key",
            redis=RedisSettings(url=""),
            api=APISettings(
                base_url="http://localhost:8080",
                api_key="test-api-key",
                max_parallel_requests=2,
            ),
        )

        # When: Creating the app
        app = create_app(settings_override=settings)

        # Then: The API client uses that worker count
        assert app.extensions["vclient"]._config.max_parallel_requests == 2

    def test_max_parallel_requests_defaults_to_four(self) -> None:
        """Verify the default worker pool stays small enough to share across requests."""
        api = APISettings(base_url="http://localhost:8080", api_key="test-api-key")
        assert api.max_parallel_requests == 4
