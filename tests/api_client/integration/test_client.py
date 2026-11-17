"""Tests for vweb.api_client.api.client."""

import httpx2
import pytest

from vweb.api_client import VClient
from vweb.api_client.constants import (
    API_KEY_HEADER,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TIMEOUT,
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_DEFAULT_COMPANY_ID,
)


class TestVClientInit:
    """Tests for VClient initialization."""

    def test_init_with_base_url_and_api_key(self):
        """Verify client initialization with custom base_url and api_key."""
        # When: Creating a client with custom values
        client = VClient(base_url="https://custom.api.com", api_key="my-key")

        # Then: Custom values are stored
        assert client._config.base_url == "https://custom.api.com"
        assert client._config.api_key == "my-key"

    def test_init_with_all_parameters(self):
        """Verify client initialization with all configuration parameters."""
        # When: Creating a client with all config options
        client = VClient(
            base_url="https://test.api.com",
            api_key="my-key",
            timeout=60.0,
            max_retries=5,
            retry_delay=2.0,
            auto_retry_rate_limit=False,
            auto_idempotency_keys=True,
            default_company_id="company-123",
            headers={"X-Custom": "value"},
        )

        # Then: All values are stored correctly
        assert client._config.timeout == 60.0
        assert client._config.max_retries == 5
        assert client._config.retry_delay == 2.0
        assert client._config.auto_retry_rate_limit is False
        assert client._config.auto_idempotency_keys is True
        assert client._config.default_company_id == "company-123"
        assert client._config.headers == {"X-Custom": "value"}

    def test_default_values(self):
        """Verify default values are applied when not specified."""
        # When: Creating a client with only required values
        client = VClient(base_url="https://test.api.com", api_key="my-key")

        # Then: Default values are used
        assert client._config.timeout == DEFAULT_TIMEOUT
        assert client._config.max_retries == DEFAULT_MAX_RETRIES
        assert client._config.retry_delay == DEFAULT_RETRY_DELAY
        assert client._config.auto_retry_rate_limit is True
        assert client._config.auto_idempotency_keys is False
        assert client._config.default_company_id is None
        assert client._config.headers == {}

    def test_auto_idempotency_keys_passed_to_config(self):
        """Verify auto_idempotency_keys parameter is passed to config."""
        # When: Creating a client with auto_idempotency_keys enabled
        client = VClient(
            base_url="https://test.api.com",
            api_key="my-key",
            auto_idempotency_keys=True,
        )

        # Then: Config has auto_idempotency_keys enabled
        assert client._config.auto_idempotency_keys is True

    @pytest.mark.parametrize(
        ("input_url", "expected"),
        [
            ("https://api.example.com/", "https://api.example.com"),
            ("https://api.example.com///", "https://api.example.com"),
            ("https://api.example.com", "https://api.example.com"),
        ],
    )
    def test_trailing_slash_normalization(self, input_url, expected):
        """Verify trailing slashes are normalized in base_url."""
        # When: Creating a client with the input URL
        client = VClient(base_url=input_url, api_key="my-key")

        # Then: URL is normalized correctly
        assert client._config.base_url == expected


class TestVClientHTTPClient:
    """Tests for VClient HTTP client configuration."""

    def test_http_client_configuration(self):
        """Verify HTTP client is properly configured with URL, headers, and API key."""
        # When: Creating a client
        client = VClient(base_url="https://test.api.com", api_key="my-key")

        # Then: HTTP client has correct base URL
        assert str(client._http.base_url) == "https://test.api.com"

        # And: HTTP client headers include the API key
        assert client._http.headers.get(API_KEY_HEADER) == "my-key"

        # And: HTTP client has Accept header (Content-Type is set per-request by httpx2)
        assert client._http.headers.get("Accept") == "application/json"

    def test_http_client_includes_custom_headers(self):
        """Verify custom headers are included in HTTP client."""
        # When: Creating a client with custom headers
        client = VClient(
            base_url="https://test.api.com",
            api_key="my-key",
            headers={"X-Custom": "custom-value"},
        )

        # Then: HTTP client includes custom headers
        assert client._http.headers.get("X-Custom") == "custom-value"

        # And: Default headers are still present
        assert client._http.headers.get("Accept") == "application/json"
        assert client._http.headers.get(API_KEY_HEADER) == "my-key"


class TestVClientContextManager:
    """Tests for VClient context manager."""

    def test_context_manager_enter(self):
        """Verify entering the context manager returns the client."""
        # When: Using client as context manager
        with VClient(base_url="https://test.api.com", api_key="my-key") as client:
            # Then: Client is returned and is open
            assert isinstance(client, VClient)
            assert not client.is_closed

    def test_context_manager_exit_closes_client(self):
        """Verify exiting the context manager closes the client."""
        # When: Exiting the context manager
        with VClient(base_url="https://test.api.com", api_key="my-key") as client:
            pass

        # Then: Client is closed
        assert client.is_closed

    def test_context_manager_closes_http_client(self):
        """Verify exiting the context manager closes the underlying sync HTTP client."""
        # When: Exiting the context manager
        with VClient(base_url="https://test.api.com", api_key="my-key") as client:
            pass

        # Then: The httpx2 client is closed
        assert isinstance(client._http, httpx2.Client)
        assert client._http.is_closed
        assert client.is_closed

    def test_close_method(self):
        """Verify close method properly closes the client."""
        # Given: An open client
        client = VClient(base_url="https://test.api.com", api_key="my-key")
        assert not client.is_closed

        # When: Calling close
        client.close()

        # Then: Client is closed
        assert client.is_closed

    def test_is_closed_property(self):
        """Verify is_closed property reflects client state."""
        # Given: An open client
        client = VClient(base_url="https://test.api.com", api_key="my-key")

        # Then: is_closed is False when open
        assert client.is_closed is False

        # When: Closing the client
        client.close()

        # Then: is_closed is True when closed
        assert client.is_closed is True


class TestVClientEnvVars:
    """Tests for VClient environment variable configuration."""

    def test_base_url_from_env_var(self, monkeypatch):
        """Verify base_url falls back to VALENTINA_CLIENT_BASE_URL env var."""
        # Given: The env var is set
        monkeypatch.setenv(ENV_BASE_URL, "https://env.api.com")

        # When: Creating a client without explicit base_url
        client = VClient(api_key="my-key")

        # Then: base_url is read from env
        assert client._config.base_url == "https://env.api.com"

    def test_api_key_from_env_var(self, monkeypatch):
        """Verify api_key falls back to VALENTINA_CLIENT_API_KEY env var."""
        # Given: The env var is set
        monkeypatch.setenv(ENV_API_KEY, "env-api-key")

        # When: Creating a client without explicit api_key
        client = VClient(base_url="https://test.api.com")

        # Then: api_key is read from env
        assert client._config.api_key == "env-api-key"

    def test_default_company_id_from_env_var(self, monkeypatch):
        """Verify default_company_id falls back to VALENTINA_CLIENT_DEFAULT_COMPANY_ID env var."""
        # Given: The env var is set
        monkeypatch.setenv(ENV_DEFAULT_COMPANY_ID, "env-company-123")

        # When: Creating a client without explicit default_company_id
        client = VClient(base_url="https://test.api.com", api_key="my-key")

        # Then: default_company_id is read from env
        assert client._config.default_company_id == "env-company-123"

    def test_all_values_from_env_vars(self, monkeypatch):
        """Verify all three env vars work together for zero-config initialization."""
        # Given: All env vars are set
        monkeypatch.setenv(ENV_BASE_URL, "https://env.api.com")
        monkeypatch.setenv(ENV_API_KEY, "env-api-key")
        monkeypatch.setenv(ENV_DEFAULT_COMPANY_ID, "env-company-123")

        # When: Creating a client with no explicit arguments
        client = VClient()

        # Then: All values are read from env
        assert client._config.base_url == "https://env.api.com"
        assert client._config.api_key == "env-api-key"
        assert client._config.default_company_id == "env-company-123"

    def test_explicit_arg_overrides_env_var(self, monkeypatch):
        """Verify explicit constructor arguments take precedence over env vars."""
        # Given: All env vars are set
        monkeypatch.setenv(ENV_BASE_URL, "https://env.api.com")
        monkeypatch.setenv(ENV_API_KEY, "env-api-key")
        monkeypatch.setenv(ENV_DEFAULT_COMPANY_ID, "env-company-123")

        # When: Creating a client with explicit arguments
        client = VClient(
            base_url="https://explicit.api.com",
            api_key="explicit-key",
            default_company_id="explicit-company",
        )

        # Then: Explicit values win
        assert client._config.base_url == "https://explicit.api.com"
        assert client._config.api_key == "explicit-key"
        assert client._config.default_company_id == "explicit-company"

    def test_missing_base_url_raises_error(self, monkeypatch):
        """Verify clear error when base_url not provided and env var not set."""
        # Given: No env var set (ensure clean)
        monkeypatch.delenv(ENV_BASE_URL, raising=False)

        # When/Then: Creating a client without base_url raises ValueError
        with pytest.raises(ValueError, match="base_url"):
            VClient(api_key="my-key")

    def test_missing_api_key_raises_error(self, monkeypatch):
        """Verify clear error when api_key not provided and env var not set."""
        # Given: No env var set (ensure clean)
        monkeypatch.delenv(ENV_API_KEY, raising=False)

        # When/Then: Creating a client without api_key raises ValueError
        with pytest.raises(ValueError, match="api_key"):
            VClient(base_url="https://test.api.com")

    def test_missing_both_required_raises_error(self, monkeypatch):
        """Verify clear error when both required values are missing."""
        # Given: No env vars set
        monkeypatch.delenv(ENV_BASE_URL, raising=False)
        monkeypatch.delenv(ENV_API_KEY, raising=False)

        # When/Then: Creating a client with no arguments raises ValueError
        with pytest.raises(ValueError):
            VClient()

    def test_default_company_id_remains_optional(self, monkeypatch):
        """Verify default_company_id is None when neither arg nor env var provided."""
        # Given: No default_company_id env var set
        monkeypatch.delenv(ENV_DEFAULT_COMPANY_ID, raising=False)

        # When: Creating a client without default_company_id
        client = VClient(base_url="https://test.api.com", api_key="my-key")

        # Then: default_company_id is None
        assert client._config.default_company_id is None
