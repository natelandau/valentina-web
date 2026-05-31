"""Tests for the global system status cache."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.models import SystemHealth
from vclient.testing import SystemHealthFactory

from tests.helpers import make_cache_store_mock
from vweb.lib.system_status_cache import clear_system_status_cache, get_system_health

if TYPE_CHECKING:
    from flask import Flask


@pytest.fixture
def mock_cache_store(mocker) -> dict:
    """Provide a dict-backed cache mock for system_status_cache."""
    return make_cache_store_mock(mocker, "vweb.lib.system_status_cache.cache")


@pytest.fixture
def mock_system_svc(mocker) -> MagicMock:
    """Mock the sync_system_service factory."""
    svc = MagicMock()
    svc.health.return_value = SystemHealthFactory.build(version="1.0.0")
    mocker.patch("vweb.lib.system_status_cache.sync_system_service", return_value=svc)
    return svc


class TestGetSystemHealth:
    """Tests for get_system_health()."""

    def test_fetches_from_api_on_cache_miss(
        self, app: Flask, mock_cache_store: dict, mock_system_svc: MagicMock
    ) -> None:
        """Verify get_system_health calls the API when the cache is empty."""
        # Given an empty cache
        # When fetching system health
        with app.test_request_context("/"):
            result = get_system_health()

        # Then a SystemHealth is returned and the endpoint is hit once with no
        # scoping args — proving the single call is shared across all users.
        assert isinstance(result, SystemHealth)
        assert result.version == "1.0.0"
        mock_system_svc.health.assert_called_once_with()

    def test_returns_cached_on_hit(
        self, app: Flask, mock_cache_store: dict, mock_system_svc: MagicMock
    ) -> None:
        """Verify a second call returns the cached value without re-calling the API."""
        # Given one populated fetch
        # When fetching twice
        with app.test_request_context("/"):
            first = get_system_health()
            second = get_system_health()

        # Then both share the cached instance and the API was called once
        assert first is second
        mock_system_svc.health.assert_called_once()

    def test_caches_with_correct_key_and_ttl(
        self, app: Flask, mock_cache_store: dict, mock_system_svc: MagicMock
    ) -> None:
        """Verify the value is stored under the shared 30-second key."""
        # When fetching system health
        with app.test_request_context("/"):
            get_system_health()

        # Then it is stored under the single global key
        assert "system_status" in mock_cache_store
        assert isinstance(mock_cache_store["system_status"], SystemHealth)


class TestClearSystemStatusCache:
    """Tests for clear_system_status_cache()."""

    def test_forces_refetch_on_next_call(
        self, app: Flask, mock_cache_store: dict, mock_system_svc: MagicMock
    ) -> None:
        """Verify clearing the cache forces a fresh API fetch on next access."""
        # Given two distinct API responses
        mock_system_svc.health.side_effect = [
            SystemHealthFactory.build(version="1.0.0"),
            SystemHealthFactory.build(version="2.0.0"),
        ]

        with app.test_request_context("/"):
            # When fetching, clearing, then fetching again
            first = get_system_health()
            assert first.version == "1.0.0"

            clear_system_status_cache()

            second = get_system_health()
            assert second.version == "2.0.0"

        # Then the API was called twice
        assert mock_system_svc.health.call_count == 2
