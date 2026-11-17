"""Tests for the global system status cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vweb.api_client.models import SystemHealth
from vweb.api_client.testing import FakeResponse, Routes, SystemHealthFactory
from vweb.lib.cache.system_status import clear, get

if TYPE_CHECKING:
    from flask import Flask

    from vweb.api_client.testing import FakeVClient


@pytest.fixture
def fake_health(real_cache_services, fake_vclient: FakeVClient) -> FakeVClient:
    """Serve a version 1.0.0 health payload from the fake API and route the cache through it."""
    fake_vclient.set_response(Routes.HEALTH_GET, model=SystemHealthFactory.build(version="1.0.0"))
    return fake_vclient


class TestGetSystemHealth:
    """Tests for get()."""

    def test_fetches_from_api_on_cache_miss(
        self, app: Flask, mock_cache_store: dict, fake_health: FakeVClient
    ) -> None:
        """Verify get calls the API when the cache is empty."""
        # Given an empty cache
        # When fetching system health
        with app.test_request_context("/"):
            result = get()

        # Then a SystemHealth is returned and the endpoint is hit once with no
        # scoping args -- proving the single call is shared across all users.
        assert isinstance(result, SystemHealth)
        assert result.version == "1.0.0"
        (request,) = fake_health.assert_called(Routes.HEALTH_GET, times=1)
        assert request.query == {}
        assert "on-behalf-of" not in request.headers

    def test_returns_cached_on_hit(
        self, app: Flask, mock_cache_store: dict, fake_health: FakeVClient
    ) -> None:
        """Verify a second call returns the cached value without re-calling the API."""
        # Given one populated fetch
        # When fetching twice
        with app.test_request_context("/"):
            first = get()
            second = get()

        # Then both share the cached instance and the API was called once
        assert first is second
        fake_health.assert_called(Routes.HEALTH_GET, times=1)

    def test_caches_with_correct_key_and_ttl(
        self, app: Flask, mock_cache_store: dict, fake_health: FakeVClient
    ) -> None:
        """Verify the value is stored under the shared 30-second key."""
        # When fetching system health
        with app.test_request_context("/"):
            get()

        # Then it is stored under the single global key
        assert "system_status" in mock_cache_store
        assert isinstance(mock_cache_store["system_status"], SystemHealth)


class TestClearSystemStatusCache:
    """Tests for clear()."""

    def test_forces_refetch_on_next_call(
        self, app: Flask, mock_cache_store: dict, fake_health: FakeVClient
    ) -> None:
        """Verify clearing the cache forces a fresh API fetch on next access."""
        # Given two distinct API responses
        fake_health.set_responses(
            Routes.HEALTH_GET,
            [
                FakeResponse(model=SystemHealthFactory.build(version="1.0.0")),
                FakeResponse(model=SystemHealthFactory.build(version="2.0.0")),
            ],
        )

        with app.test_request_context("/"):
            # When fetching, clearing, then fetching again
            first = get()
            assert first.version == "1.0.0"

            clear()

            second = get()
            assert second.version == "2.0.0"

        # Then the API was called twice
        fake_health.assert_called(Routes.HEALTH_GET, times=2)
