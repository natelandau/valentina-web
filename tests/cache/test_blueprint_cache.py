"""Tests for global blueprint trait cache."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from tests.helpers import seed_session
from vweb.api_client.testing import (
    FakeResponse,
    Routes,
    TraitFactory,
    TraitSubcategoryFactory,
)
from vweb.lib.cache.blueprint import (
    clear,
    subcategories,
    trait,
    traits,
)

COMPANY = {"company_id": "test-company-id"}


class TestTraits:
    """Tests for traits()."""

    def test_fetches_from_api_on_cache_miss(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify traits calls the API when the cache is empty."""
        # Given two traits returned by the API
        trait_list = TraitFactory.batch(2)
        fake_vclient.set_response(Routes.BLUEPRINT_TRAITS_LIST, items=trait_list)

        # When fetching all traits
        with app.test_request_context("/"):
            seed_session()
            result = traits()

        # Then the result is a dict keyed by trait ID
        assert result == {t.id: t for t in trait_list}
        fake_vclient.assert_called(Routes.BLUEPRINT_TRAITS_LIST, params=COMPANY, times=1)

    def test_returns_cached_on_hit(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify traits returns cached dict without calling the API again."""
        # Given traits are already cached from a first call
        fake_vclient.set_response(Routes.BLUEPRINT_TRAITS_LIST, items=TraitFactory.batch(2))

        with app.test_request_context("/"):
            seed_session()
            first = traits()
            second = traits()

        # Then the API is called only once and both results are the same dict
        assert first is second
        fake_vclient.assert_called(Routes.BLUEPRINT_TRAITS_LIST, times=1)

    def test_returns_empty_dict_when_no_traits(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify traits returns an empty dict when the API returns no traits."""
        # Given the API returns an empty list
        fake_vclient.set_response(Routes.BLUEPRINT_TRAITS_LIST, items=[])

        # When fetching all traits
        with app.test_request_context("/"):
            seed_session()
            result = traits()

        # Then the result is an empty dict
        assert result == {}


class TestTrait:
    """Tests for trait()."""

    def test_returns_trait_for_known_id(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify trait returns the correct Trait for a known ID."""
        # Given a trait exists in the cache
        t = TraitFactory.build(id="trait-1", name="Strength")
        fake_vclient.set_response(Routes.BLUEPRINT_TRAITS_LIST, items=[t])

        # When looking up by ID
        with app.test_request_context("/"):
            seed_session()
            result = trait("trait-1")

        # Then the trait is returned
        assert result == t

    def test_returns_none_for_unknown_id(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify trait returns None for an unknown trait ID."""
        # Given the cache has traits but not the requested one
        fake_vclient.set_response(
            Routes.BLUEPRINT_TRAITS_LIST, items=[TraitFactory.build(id="other")]
        )

        # When looking up an unknown ID
        with app.test_request_context("/"):
            seed_session()
            result = trait("nonexistent")

        # Then None is returned
        assert result is None


class TestClear:
    """Tests for clear()."""

    def test_forces_refetch_on_next_call(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify clear forces a fresh API fetch on next access."""
        # Given traits are cached
        fake_vclient.set_responses(
            Routes.BLUEPRINT_TRAITS_LIST,
            [
                FakeResponse(items=TraitFactory.batch(2)),
                FakeResponse(items=TraitFactory.batch(3)),
            ],
        )

        with app.test_request_context("/"):
            seed_session()
            first = traits()
            assert len(first) == 2

            # When the cache is cleared
            clear()

            # Then the next call fetches fresh data
            second = traits()
            assert len(second) == 3

        fake_vclient.assert_called(Routes.BLUEPRINT_TRAITS_LIST, times=2)

    def test_clears_both_traits_and_subcategories(
        self, app, mock_cache_store, fake_vclient
    ) -> None:
        """Verify clear evicts both the traits and subcategory cache keys."""
        # Given both caches are populated
        fake_vclient.set_responses(
            Routes.BLUEPRINT_TRAITS_LIST,
            [
                FakeResponse(items=TraitFactory.batch(2)),
                FakeResponse(items=TraitFactory.batch(3)),
            ],
        )
        fake_vclient.set_responses(
            Routes.BLUEPRINT_SUBCATEGORIES_LIST,
            [
                FakeResponse(items=TraitSubcategoryFactory.batch(1)),
                FakeResponse(items=TraitSubcategoryFactory.batch(2)),
            ],
        )

        with app.test_request_context("/"):
            seed_session()

            # Populate both caches
            first_traits = traits()
            first_subcats = subcategories()
            assert len(first_traits) == 2
            assert len(first_subcats) == 1

            # When the cache is cleared
            clear()

            # Then both caches are re-fetched on next access
            second_traits = traits()
            second_subcats = subcategories()
            assert len(second_traits) == 3
            assert len(second_subcats) == 2

        fake_vclient.assert_called(Routes.BLUEPRINT_TRAITS_LIST, times=2)
        fake_vclient.assert_called(Routes.BLUEPRINT_SUBCATEGORIES_LIST, times=2)


class TestSubcategories:
    """Tests for subcategories()."""

    def test_fetches_from_api_on_cache_miss(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify subcategories calls the API when the cache is empty."""
        # Given two subcategories returned by the API
        subcategory_list = TraitSubcategoryFactory.batch(2)
        fake_vclient.set_response(Routes.BLUEPRINT_SUBCATEGORIES_LIST, items=subcategory_list)

        # When fetching all subcategories
        with app.test_request_context("/"):
            seed_session()
            result = subcategories()

        # Then the result is a dict keyed by subcategory ID
        assert result == {sc.id: sc for sc in subcategory_list}
        fake_vclient.assert_called(Routes.BLUEPRINT_SUBCATEGORIES_LIST, params=COMPANY, times=1)

    def test_returns_cached_on_hit(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify subcategories returns the cached dict without re-fetching."""
        # Given subcategories cached from a first call
        fake_vclient.set_response(
            Routes.BLUEPRINT_SUBCATEGORIES_LIST, items=TraitSubcategoryFactory.batch(1)
        )

        with app.test_request_context("/"):
            seed_session()
            first = subcategories()
            second = subcategories()

        # Then the API is called only once and both results are the same dict
        assert first is second
        fake_vclient.assert_called(Routes.BLUEPRINT_SUBCATEGORIES_LIST, times=1)


class TestSingleFlight:
    """Tests that concurrent cold-cache fetches collapse into one API call."""

    def test_single_flight_collapses_concurrent_trait_fetches(self, app, mocker) -> None:
        """Verify two concurrent cold fetches of all traits trigger exactly one API call."""
        from vweb.extensions import cache as flask_cache

        # Given a real (dict-pickling) cache cleared to a cold state
        with app.app_context():
            flask_cache.clear()

        trait_list = TraitFactory.batch(2)

        # Given a fetch that blocks so the second thread must queue behind it
        fetch_count = 0
        entered = threading.Event()
        release = threading.Event()

        def blocking_list_all_traits() -> list:
            nonlocal fetch_count
            fetch_count += 1
            entered.set()
            # Block so the second thread is forced to wait on the single-flight lock,
            # making the race deterministic rather than timing-dependent.
            release.wait(timeout=5)
            return trait_list

        svc = MagicMock()
        svc.list_all_traits.side_effect = blocking_list_all_traits
        mocker.patch("vweb.lib.cache.blueprint.api_services.character_blueprint", return_value=svc)

        results: dict[str, dict] = {}

        def worker(name: str) -> None:
            with app.test_request_context("/"):
                seed_session()
                results[name] = traits()

        # When thread A enters the rebuild and blocks, then thread B starts and queues
        thread_a = threading.Thread(target=worker, args=("a",))
        thread_a.start()
        assert entered.wait(timeout=5), "thread A never entered list_all_traits"

        thread_b = threading.Thread(target=worker, args=("b",))
        thread_b.start()
        # Give B a moment to reach and block on the single-flight lock before releasing A.
        threading.Event().wait(0.1)
        release.set()

        thread_a.join(timeout=5)
        thread_b.join(timeout=5)

        # Then both threads finished without hanging
        assert not thread_a.is_alive(), "thread A hung"
        assert not thread_b.is_alive(), "thread B hung"

        # Then exactly one fetch ran; thread B reused the built dict via the double-check.
        # SimpleCache pickles on set/get, so B's copy is equal but not identical.
        assert fetch_count == 1
        assert results["a"] == results["b"]
        assert len(results["a"]) == 2
