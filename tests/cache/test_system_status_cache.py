"""Tests for the global system status cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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


def test_one_unscoped_fetch_shared_by_all_users(
    app: Flask, mock_cache_store: dict, fake_health: FakeVClient
) -> None:
    """Verify system health is fetched once, with no user or company scope, then cached."""
    with app.test_request_context("/"):
        first = get()
        second = get()

    assert first is second
    assert first.version == "1.0.0"
    (request,) = fake_health.assert_called(Routes.HEALTH_GET, times=1)
    assert request.query == {}
    assert "on-behalf-of" not in request.headers


def test_clear_forces_refetch(app: Flask, mock_cache_store: dict, fake_health: FakeVClient) -> None:
    """Verify clearing the cache forces a fresh API fetch on next access."""
    fake_health.set_responses(
        Routes.HEALTH_GET,
        [
            FakeResponse(model=SystemHealthFactory.build(version="1.0.0")),
            FakeResponse(model=SystemHealthFactory.build(version="2.0.0")),
        ],
    )

    with app.test_request_context("/"):
        assert get().version == "1.0.0"

        clear()

        assert get().version == "2.0.0"

    fake_health.assert_called(Routes.HEALTH_GET, times=2)
