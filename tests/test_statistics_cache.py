"""Tests for the generic statistics cache helper."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.testing import RollStatisticsFactory

from vweb.lib.statistics_cache import get_statistics

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestGetStatistics:
    """Tests for get_statistics(scope_type, scope_id)."""

    def test_campaign_scope_calls_campaigns_service(self, app, mocker: MockerFixture) -> None:
        """Verify campaign scope dispatches to sync_campaigns_service.get_statistics."""
        # Given a mocked campaigns service
        stats = RollStatisticsFactory.build()
        svc = MagicMock()
        svc.get_statistics.return_value = stats
        mock_factory = mocker.patch(
            "vweb.lib.statistics_cache.sync_campaigns_service", autospec=True
        )
        mock_factory.return_value = svc

        # When requesting campaign-scoped statistics
        with app.test_request_context():
            from flask import g, session

            g.requesting_user = MagicMock(id="user-1")
            session["company_id"] = "comp-1"
            result = get_statistics("campaign", "camp-1")

        # Then the campaigns service is called with the right ID and num_top_traits=1
        svc.get_statistics.assert_called_once_with("camp-1", num_top_traits=1)
        assert result is stats

    def test_user_scope_calls_users_service(self, app, mocker: MockerFixture) -> None:
        """Verify user scope dispatches to sync_users_service.get_statistics."""
        # Given a mocked users service
        stats = RollStatisticsFactory.build()
        svc = MagicMock()
        svc.get_statistics.return_value = stats
        mock_factory = mocker.patch("vweb.lib.statistics_cache.sync_users_service", autospec=True)
        mock_factory.return_value = svc

        # When requesting user-scoped statistics
        with app.test_request_context():
            from flask import g, session

            g.requesting_user = MagicMock(id="user-1")
            session["company_id"] = "comp-1"
            result = get_statistics("user", "user-2")

        # Then the users service is called with the right ID
        svc.get_statistics.assert_called_once_with("user-2", num_top_traits=1)
        assert result is stats

    def test_character_scope_calls_characters_service(self, app, mocker: MockerFixture) -> None:
        """Verify character scope dispatches to sync_characters_service.get_statistics."""
        # Given a mocked characters service
        stats = RollStatisticsFactory.build()
        svc = MagicMock()
        svc.get_statistics.return_value = stats
        mock_factory = mocker.patch(
            "vweb.lib.statistics_cache.sync_characters_service", autospec=True
        )
        mock_factory.return_value = svc

        # When requesting character-scoped statistics
        with app.test_request_context():
            from flask import g, session

            g.requesting_user = MagicMock(id="user-1")
            session["company_id"] = "comp-1"
            result = get_statistics("character", "char-1")

        # Then the characters service is called with the right ID
        svc.get_statistics.assert_called_once_with("char-1", num_top_traits=1)
        assert result is stats

    def test_cache_hit_returns_without_api_call(self, mocker: MockerFixture) -> None:
        """Verify a cache hit skips the API call entirely."""
        # Given a value already in the cache
        stats = RollStatisticsFactory.build()
        mocker.patch("vweb.lib.statistics_cache.cache.get", return_value=stats)
        svc = MagicMock()
        mock_factory = mocker.patch(
            "vweb.lib.statistics_cache.sync_campaigns_service", autospec=True
        )
        mock_factory.return_value = svc

        # When requesting statistics (no Flask context — cache hit happens before Flask state)
        result = get_statistics("campaign", "camp-1")

        # Then no API call was made and the cached value is returned
        svc.get_statistics.assert_not_called()
        assert result is stats

    def test_unknown_scope_type_raises(self, app) -> None:
        """Verify an unknown scope_type raises ValueError."""
        with app.test_request_context(), pytest.raises(ValueError, match="scope_type"):
            get_statistics("bogus", "id-1")
