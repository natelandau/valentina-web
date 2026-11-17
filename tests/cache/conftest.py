"""Fixtures shared by the cache domain tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vweb.api_client import system_service
from vweb.lib import api_services

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.fixture
def real_cache_services(mocker: MockerFixture) -> None:
    """Route the cache domains through the real services so `fake_vclient` serves them.

    The autouse `_mock_api` fixture replaces these modules' service accessors with mocks
    so page renders never reach the API. Tests of the caches themselves undo that.
    """
    for module in ("dictionary", "campaign_content", "options"):
        mocker.patch(f"vweb.lib.cache.{module}.api_services", api_services)
    mocker.patch("vweb.lib.cache.system_status.system_service", system_service)
