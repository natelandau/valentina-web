"""Tests for global blueprint trait cache."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import TraitFactory

from tests.helpers import make_cache_store_mock
from vweb.lib.blueprint_cache import clear_blueprint_cache, get_all_traits, get_trait


@pytest.fixture
def mock_cache_store(mocker) -> dict:
    """Provide a dict-backed cache mock for blueprint_cache."""
    return make_cache_store_mock(mocker, "vweb.lib.blueprint_cache.cache")


@pytest.fixture
def mock_bp_svc(mocker):
    """Mock the sync_character_blueprint_service factory."""
    svc = MagicMock()
    mocker.patch("vweb.lib.blueprint_cache.sync_character_blueprint_service", return_value=svc)
    return svc


class TestGetAllTraits:
    """Tests for get_all_traits()."""

    def test_fetches_from_api_on_cache_miss(self, app, mock_cache_store, mock_bp_svc) -> None:
        """Verify get_all_traits calls the API when the cache is empty."""
        # Given two traits returned by the API
        traits = TraitFactory.batch(2)
        mock_bp_svc.list_all_traits.return_value = traits

        # When fetching all traits
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            result = get_all_traits()

        # Then the result is a dict keyed by trait ID
        assert len(result) == 2
        for t in traits:
            assert result[t.id] is t
        mock_bp_svc.list_all_traits.assert_called_once()

    def test_returns_cached_on_hit(self, app, mock_cache_store, mock_bp_svc) -> None:
        """Verify get_all_traits returns cached dict without calling the API again."""
        # Given traits are already cached from a first call
        traits = TraitFactory.batch(2)
        mock_bp_svc.list_all_traits.return_value = traits

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            first = get_all_traits()
            second = get_all_traits()

        # Then the API is called only once and both results are the same dict
        assert first is second
        mock_bp_svc.list_all_traits.assert_called_once()

    def test_returns_empty_dict_when_no_traits(self, app, mock_cache_store, mock_bp_svc) -> None:
        """Verify get_all_traits returns an empty dict when the API returns no traits."""
        # Given the API returns an empty list
        mock_bp_svc.list_all_traits.return_value = []

        # When fetching all traits
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            result = get_all_traits()

        # Then the result is an empty dict
        assert result == {}


class TestGetTrait:
    """Tests for get_trait()."""

    def test_returns_trait_for_known_id(self, app, mock_cache_store, mock_bp_svc) -> None:
        """Verify get_trait returns the correct Trait for a known ID."""
        # Given a trait exists in the cache
        trait = TraitFactory.build(id="trait-1", name="Strength")
        mock_bp_svc.list_all_traits.return_value = [trait]

        # When looking up by ID
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            result = get_trait("trait-1")

        # Then the trait is returned
        assert result is trait

    def test_returns_none_for_unknown_id(self, app, mock_cache_store, mock_bp_svc) -> None:
        """Verify get_trait returns None for an unknown trait ID."""
        # Given the cache has traits but not the requested one
        mock_bp_svc.list_all_traits.return_value = [TraitFactory.build(id="other")]

        # When looking up an unknown ID
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            result = get_trait("nonexistent")

        # Then None is returned
        assert result is None


class TestClearBlueprintCache:
    """Tests for clear_blueprint_cache()."""

    def test_forces_refetch_on_next_call(self, app, mock_cache_store, mock_bp_svc) -> None:
        """Verify clear_blueprint_cache forces a fresh API fetch on next access."""
        # Given traits are cached
        traits_v1 = TraitFactory.batch(2)
        traits_v2 = TraitFactory.batch(3)
        mock_bp_svc.list_all_traits.side_effect = [traits_v1, traits_v2]

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            first = get_all_traits()
            assert len(first) == 2

            # When the cache is cleared
            clear_blueprint_cache()

            # Then the next call fetches fresh data
            second = get_all_traits()
            assert len(second) == 3

        assert mock_bp_svc.list_all_traits.call_count == 2
