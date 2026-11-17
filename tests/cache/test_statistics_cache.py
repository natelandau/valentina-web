"""Tests for the generic statistics cache helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import RollStatisticsFactory, Routes
from vweb.lib.cache.statistics import get

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from vweb.api_client.testing import FakeVClient


class TestGetStatistics:
    """Tests for get(scope_type, scope_id)."""

    def test_campaign_scope_calls_campaigns_service(self, app, fake_vclient: FakeVClient) -> None:
        """Verify campaign scope requests the campaign's statistics."""
        # Given campaign statistics on the API
        stats = RollStatisticsFactory.build()
        fake_vclient.set_response(Routes.CAMPAIGNS_STATISTICS, model=stats)

        # When requesting campaign-scoped statistics
        with app.test_request_context():
            seed_session(user_id="user-1", company_id="comp-1")
            result = get("campaign", "camp-1")

        # Then the campaign's statistics are requested with num_top_traits=1
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_STATISTICS,
            params={"company_id": "comp-1", "campaign_id": "camp-1"},
            query={"num_top_traits": 1},
            times=1,
        )
        assert result == stats

    def test_user_scope_calls_users_service(self, app, fake_vclient: FakeVClient) -> None:
        """Verify user scope requests the user's statistics."""
        # Given user statistics on the API
        stats = RollStatisticsFactory.build()
        fake_vclient.set_response(Routes.USERS_STATISTICS, model=stats)

        # When requesting user-scoped statistics
        with app.test_request_context():
            seed_session(user_id="user-1", company_id="comp-1")
            result = get("user", "user-2")

        # Then the requested user's statistics are fetched
        fake_vclient.assert_called(
            Routes.USERS_STATISTICS,
            params={"company_id": "comp-1", "user_id": "user-2"},
            query={"num_top_traits": 1},
            times=1,
        )
        assert result == stats

    def test_character_scope_calls_characters_service(self, app, fake_vclient: FakeVClient) -> None:
        """Verify character scope requests the character's statistics."""
        # Given character statistics on the API
        stats = RollStatisticsFactory.build()
        fake_vclient.set_response(Routes.CHARACTERS_STATISTICS, model=stats)

        # When requesting character-scoped statistics
        with app.test_request_context():
            seed_session(user_id="user-1", company_id="comp-1")
            result = get("character", "char-1")

        # Then the character's statistics are fetched
        fake_vclient.assert_called(
            Routes.CHARACTERS_STATISTICS,
            params={"company_id": "comp-1", "character_id": "char-1"},
            query={"num_top_traits": 1},
            times=1,
        )
        assert result == stats

    def test_cache_hit_returns_without_api_call(
        self, app, mocker: MockerFixture, fake_vclient: FakeVClient
    ) -> None:
        """Verify a cache hit skips the API call entirely."""
        # Given a value already in the cache
        stats = RollStatisticsFactory.build()
        mocker.patch("vweb.lib.cache.base.cache.get", return_value=stats)

        # When requesting statistics (cache hit happens before Flask state needed)
        with app.app_context():
            result = get("campaign", "camp-1")

        # Then no API call was made and the cached value is returned
        assert fake_vclient.requests == []
        assert result is stats

    def test_unknown_scope_type_raises(self, app) -> None:
        """Verify an unknown scope_type raises ValueError."""
        with app.test_request_context(), pytest.raises(ValueError, match="scope_type"):
            get("bogus", "id-1")
