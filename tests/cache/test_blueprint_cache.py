"""Tests for global blueprint trait cache."""

from __future__ import annotations

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import (
    CharacterConceptFactory,
    FakeResponse,
    Routes,
    TraitFactory,
    TraitSubcategoryFactory,
)
from vweb.lib.cache.blueprint import (
    clear,
    concept,
    subcategories,
    subcategory,
    trait,
    traits,
)

COMPANY = {"company_id": "test-company-id"}


@pytest.mark.parametrize(
    ("route", "factory", "read"),
    [
        pytest.param(Routes.BLUEPRINT_TRAITS_LIST, TraitFactory, traits, id="traits"),
        pytest.param(
            Routes.BLUEPRINT_SUBCATEGORIES_LIST,
            TraitSubcategoryFactory,
            subcategories,
            id="subcategories",
        ),
    ],
)
def test_fetches_once_keyed_by_id(
    app, mock_cache_store, fake_vclient, route, factory, read
) -> None:
    """Verify the company's blueprint list is fetched once, then served from cache by id."""
    items = factory.batch(2)
    fake_vclient.set_response(route, items=items)

    with app.test_request_context("/"):
        seed_session()
        first = read()
        second = read()

    assert first == second == {item.id: item for item in items}
    fake_vclient.assert_called(route, params=COMPANY, times=1)


@pytest.mark.parametrize(
    ("route", "factory", "lookup"),
    [
        pytest.param(Routes.BLUEPRINT_TRAITS_LIST, TraitFactory, trait, id="trait"),
        pytest.param(
            Routes.BLUEPRINT_SUBCATEGORIES_LIST,
            TraitSubcategoryFactory,
            subcategory,
            id="subcategory",
        ),
    ],
)
def test_lookup_by_id(app, mock_cache_store, fake_vclient, route, factory, lookup) -> None:
    """Verify a single blueprint entry is found by id, and None for an unknown id."""
    item = factory.build(id="known")
    fake_vclient.set_response(route, items=[item])

    with app.test_request_context("/"):
        seed_session()

        assert lookup("known") == item
        assert lookup("unknown") is None


def test_clear_forces_refetch_of_traits_and_subcategories(
    app, mock_cache_store, fake_vclient
) -> None:
    """Verify clear evicts both blueprint caches so the next read fetches fresh data."""
    fake_vclient.set_responses(
        Routes.BLUEPRINT_TRAITS_LIST,
        [FakeResponse(items=TraitFactory.batch(2)), FakeResponse(items=TraitFactory.batch(3))],
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
        assert (len(traits()), len(subcategories())) == (2, 1)

        clear()

        assert (len(traits()), len(subcategories())) == (3, 2)

    fake_vclient.assert_called(Routes.BLUEPRINT_TRAITS_LIST, times=2)
    fake_vclient.assert_called(Routes.BLUEPRINT_SUBCATEGORIES_LIST, times=2)


class TestConcept:
    """Tests for concept()."""

    def test_fetches_concepts_once_and_looks_up_by_id(
        self, app, mock_cache_store, fake_vclient
    ) -> None:
        """Verify concept() reads one cached list for every lookup."""
        # Given the API lists two concepts
        healer, soldier = CharacterConceptFactory.batch(2)
        fake_vclient.set_response(Routes.BLUEPRINT_CONCEPTS_LIST, items=[healer, soldier])

        # When looking up both concepts
        with app.test_request_context("/"):
            seed_session()
            found = [concept(healer.id), concept(soldier.id)]

        # Then both are found with a single API request
        assert found == [healer, soldier]
        fake_vclient.assert_called(Routes.BLUEPRINT_CONCEPTS_LIST, params=COMPANY, times=1)

    def test_returns_none_without_an_id(self, app, mock_cache_store, fake_vclient) -> None:
        """Verify a character without a concept costs no API request."""
        with app.test_request_context("/"):
            seed_session()
            result = concept(None)

        assert result is None
        fake_vclient.assert_not_called(Routes.BLUEPRINT_CONCEPTS_LIST)
