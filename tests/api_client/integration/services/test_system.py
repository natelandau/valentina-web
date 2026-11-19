"""Tests for vweb.api_client.services.system."""

import pytest
import respx

from vweb.api_client.endpoints import Endpoints


@pytest.mark.parametrize(
    "response_data",
    [
        pytest.param(
            {
                "database_status": "online",
                "cache_status": "online",
                "database_latency_ms": 1.2,
                "cache_latency_ms": 0.5,
                "uptime": "3d 12h 45m",
                "version": "0.7.0",
            },
            id="all-online",
        ),
        pytest.param(
            {
                "database_status": "offline",
                "cache_status": "offline",
                "database_latency_ms": None,
                "cache_latency_ms": None,
                "uptime": "0d 0h 1m",
                "version": "0.7.0",
            },
            id="all-offline",
        ),
    ],
)
@respx.mock
def test_health(vclient, base_url, response_data):
    """Verify health parses the API's status, with no latency for an offline service."""
    route = respx.get(f"{base_url}{Endpoints.HEALTH}").respond(200, json=response_data)

    result = vclient.system.health()

    assert route.called
    assert result.model_dump() == response_data
