"""Tests for vweb.api_client.api.client."""

import pytest
import respx

from vweb.api_client import VClient
from vweb.api_client.constants import API_KEY_HEADER, USER_AGENT_PRODUCT
from vweb.api_client.services.base import BaseService


class TestVClientInit:
    """Tests for VClient initialization."""

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

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"base_url": "", "api_key": "my-key"}, "base_url"),
            ({"base_url": "https://test.api.com", "api_key": ""}, "api_key"),
        ],
    )
    def test_empty_required_arg_raises_error(self, kwargs, match):
        """Verify an empty base_url or api_key raises ValueError naming the argument."""
        with pytest.raises(ValueError, match=match):
            VClient(**kwargs)


class TestVClientHTTPClient:
    """Tests for VClient HTTP client configuration."""

    @respx.mock
    def test_requests_carry_default_headers_and_timeout(self):
        """Verify requests go to the base URL with the API key, Accept, and User-Agent headers."""
        # Given: A mocked endpoint and a client with a custom timeout
        route = respx.get("https://test.api.com/ping").respond(200, json={})

        with VClient(base_url="https://test.api.com", api_key="my-key", timeout=60.0) as client:
            # When: Making a request
            BaseService(client)._get("/ping")

            # Then: The configured timeout reaches the HTTP client
            assert client._http.timeout.read == 60.0

        # Then: The request carried the default headers
        headers = route.calls.last.request.headers
        assert headers[API_KEY_HEADER] == "my-key"
        assert headers["Accept"] == "application/json"
        assert headers["User-Agent"].startswith(USER_AGENT_PRODUCT)


class TestVClientContextManager:
    """Tests for VClient context manager and close."""

    def test_context_manager_closes_client_on_exit(self):
        """Verify the context manager yields an open client and closes it on exit."""
        # When: Using the client as a context manager
        with VClient(base_url="https://test.api.com", api_key="my-key") as client:
            # Then: The client is open inside the block
            assert not client.is_closed

        # Then: The client and its HTTP client are closed after the block
        assert client.is_closed
        assert client._http.is_closed

    def test_close_method(self):
        """Verify close closes an open client."""
        # Given: An open client
        client = VClient(base_url="https://test.api.com", api_key="my-key")
        assert client.is_closed is False

        # When: Calling close
        client.close()

        # Then: Client is closed
        assert client.is_closed is True


class TestVClientUnscopedServices:
    """The unscoped services are built once per client and reused."""

    @pytest.mark.parametrize("name", ["companies", "system", "user_lookup"])
    def test_service_is_reused(self, name):
        """Verify each access returns the same service instance."""
        with VClient(base_url="https://test.api.com", api_key="my-key") as client:
            assert getattr(client, name) is getattr(client, name)

    def test_default_company_id_is_exposed(self):
        """Verify the configured default company id is readable from the client."""
        with VClient(
            base_url="https://test.api.com", api_key="my-key", default_company_id="comp-1"
        ) as client:
            assert client.default_company_id == "comp-1"
