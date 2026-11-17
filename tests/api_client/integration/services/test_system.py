"""Tests for vweb.api_client.services.system."""

import pytest
import respx

from vweb.api_client import VClient
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import SystemHealth
from vweb.api_client.registry import configure_default_client, system_service
from vweb.api_client.services import SystemService


@pytest.fixture
def health_response_data() -> dict:
    """Return health response data with every field set, so tests can assert parsing."""
    return {
        "database_status": "online",
        "cache_status": "online",
        "database_latency_ms": 1.2,
        "cache_latency_ms": 0.5,
        "uptime": "3d 12h 45m",
        "version": "0.7.0",
    }


class TestSystemServiceHealth:
    """Tests for SystemService.health method."""

    @respx.mock
    def test_health_returns_system_health(self, vclient, base_url, health_response_data):
        """Verify health returns SystemHealth object."""
        # Given: A mocked health endpoint
        route = respx.get(f"{base_url}{Endpoints.HEALTH}").respond(200, json=health_response_data)

        # When: Calling health
        result = vclient.system.health()

        # Then: Returns SystemHealth object with correct data
        assert route.called
        assert isinstance(result, SystemHealth)
        assert result.database_status == "online"
        assert result.cache_status == "online"
        assert result.database_latency_ms == 1.2
        assert result.cache_latency_ms == 0.5
        assert result.uptime == "3d 12h 45m"
        assert result.version == "0.7.0"

    @respx.mock
    def test_health_with_offline_database(self, vclient, base_url):
        """Verify health correctly reports offline database."""
        # Given: A mocked endpoint with offline database
        response_data = {
            "database_status": "offline",
            "cache_status": "online",
            "database_latency_ms": None,
            "cache_latency_ms": 0.5,
            "uptime": "1d 0h 0m",
            "version": "0.7.0",
        }
        route = respx.get(f"{base_url}{Endpoints.HEALTH}").respond(200, json=response_data)

        # When: Calling health
        result = vclient.system.health()

        # Then: Returns correct offline status
        assert route.called
        assert result.database_status == "offline"
        assert result.cache_status == "online"
        assert result.database_latency_ms is None

    @respx.mock
    def test_health_with_offline_cache(self, vclient, base_url):
        """Verify health correctly reports offline cache."""
        # Given: A mocked endpoint with offline cache
        response_data = {
            "database_status": "online",
            "cache_status": "offline",
            "database_latency_ms": 1.0,
            "cache_latency_ms": None,
            "uptime": "1d 0h 0m",
            "version": "0.7.0",
        }
        route = respx.get(f"{base_url}{Endpoints.HEALTH}").respond(200, json=response_data)

        # When: Calling health
        result = vclient.system.health()

        # Then: Returns correct offline status
        assert route.called
        assert result.database_status == "online"
        assert result.cache_status == "offline"
        assert result.cache_latency_ms is None

    @respx.mock
    def test_health_with_all_services_offline(self, vclient, base_url):
        """Verify health correctly reports all services offline."""
        # Given: A mocked endpoint with all services offline
        response_data = {
            "database_status": "offline",
            "cache_status": "offline",
            "database_latency_ms": None,
            "cache_latency_ms": None,
            "uptime": "0d 0h 1m",
            "version": "0.7.0",
        }
        route = respx.get(f"{base_url}{Endpoints.HEALTH}").respond(200, json=response_data)

        # When: Calling health
        result = vclient.system.health()

        # Then: Returns correct offline status for all services
        assert route.called
        assert result.database_status == "offline"
        assert result.cache_status == "offline"


class TestSystemServiceClientIntegration:
    """Tests for VClient.system property."""

    def test_system_property_returns_service(self, vclient):
        """Verify system property returns SystemService instance."""
        # When: Accessing the system property
        service = vclient.system

        # Then: Returns a SystemService instance
        assert isinstance(service, SystemService)

    def test_system_property_cached(self, vclient):
        """Verify system property returns same instance on multiple calls."""
        # When: Accessing the system property multiple times
        service1 = vclient.system
        service2 = vclient.system

        # Then: Returns the same instance
        assert service1 is service2


class TestDefaultClientSystemHealth:
    """End-to-end tests for the default client registry with the system service."""

    @respx.mock
    def test_default_client_health_returns_system_health(
        self, base_url, api_key, health_response_data
    ):
        """Verify system_service() issues the request through the registered default client."""
        # Given: A VClient registered as the default and a mocked health endpoint
        route = respx.get(f"{base_url}{Endpoints.HEALTH}").respond(200, json=health_response_data)
        with VClient(base_url=base_url, api_key=api_key) as client:
            configure_default_client(client)
            # When: Calling health through the default service accessor
            result = system_service().health()

        # Then: The mocked values are parsed into SystemHealth
        assert route.called
        assert isinstance(result, SystemHealth)
        assert result.database_status == "online"
        assert result.version == "0.7.0"
