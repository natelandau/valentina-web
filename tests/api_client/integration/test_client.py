"""Tests for vweb.api_client.api.client."""

import httpx2
import pytest

from vweb.api_client import VClient
from vweb.api_client.constants import (
    API_KEY_HEADER,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TIMEOUT,
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
        )

        # Then: All values are stored correctly
        assert client._config.timeout == 60.0
        assert client._config.max_retries == 5
        assert client._config.retry_delay == 2.0
        assert client._config.auto_retry_rate_limit is False
        assert client._config.auto_idempotency_keys is True
        assert client._config.default_company_id == "company-123"

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

    def test_http_client_includes_default_headers(self):
        """Verify the HTTP client sends the Accept and API key headers."""
        client = VClient(base_url="https://test.api.com", api_key="my-key")

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


class TestVClientRequiredArgs:
    """Tests for VClient's required connection arguments."""

    def test_empty_base_url_raises_error(self):
        """Verify an empty base_url raises ValueError."""
        with pytest.raises(ValueError, match="base_url"):
            VClient(base_url="", api_key="my-key")

    def test_empty_api_key_raises_error(self):
        """Verify an empty api_key raises ValueError."""
        with pytest.raises(ValueError, match="api_key"):
            VClient(base_url="https://test.api.com", api_key="")
