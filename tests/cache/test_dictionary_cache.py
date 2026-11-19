"""Tests for global dictionary term cache."""

from __future__ import annotations

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import DictionaryTermFactory, FakeResponse, Routes
from vweb.lib.cache.dictionary import clear, search, term, terms

pytestmark = pytest.mark.usefixtures("real_cache_services")


def test_terms_fetched_once_and_sorted(app, mock_cache_store, fake_vclient) -> None:
    """Verify the company's terms are fetched once and sorted by name, ignoring case."""
    names = ["zephyr", "Amaranth", "Beast"]
    fake_vclient.set_response(
        Routes.DICTIONARY_LIST, items=[DictionaryTermFactory.build(term=n) for n in names]
    )

    with app.test_request_context("/"):
        seed_session()
        first = terms()
        second = terms()

    assert [t.term for t in first] == ["Amaranth", "Beast", "zephyr"]
    assert second is first
    fake_vclient.assert_called(
        Routes.DICTIONARY_LIST, params={"company_id": "test-company-id"}, times=1
    )


def test_term_lookup_by_id(app, mock_cache_store, fake_vclient) -> None:
    """Verify a term is found by id, and None for an unknown id."""
    known = DictionaryTermFactory.build(id="term-1")
    fake_vclient.set_response(Routes.DICTIONARY_LIST, items=[known])

    with app.test_request_context("/"):
        seed_session()

        assert term("term-1") == known
        assert term("nonexistent") is None


def test_clear_forces_refetch(app, mock_cache_store, fake_vclient) -> None:
    """Verify clear forces a fresh API fetch on next access."""
    fake_vclient.set_responses(
        Routes.DICTIONARY_LIST,
        [
            FakeResponse(items=DictionaryTermFactory.batch(2)),
            FakeResponse(items=DictionaryTermFactory.batch(3)),
        ],
    )

    with app.test_request_context("/"):
        seed_session()
        assert len(terms()) == 2

        clear()

        assert len(terms()) == 3

    fake_vclient.assert_called(Routes.DICTIONARY_LIST, times=2)


_SEARCH_TERMS = [
    ("Amaranth", []),
    ("Auspex", ["heightened senses", "auspicious"]),
    ("Beast", ["The Monster"]),
]


@pytest.mark.parametrize(
    ("query", "include_synonyms", "expected"),
    [
        pytest.param("aus", False, ["Auspex"], id="substring"),
        pytest.param("AUS", False, ["Auspex"], id="case-insensitive"),
        pytest.param("", False, ["Amaranth", "Auspex", "Beast"], id="empty-query-all"),
        pytest.param("", True, ["Amaranth", "Auspex", "Beast"], id="empty-query-all-synonyms"),
        pytest.param("zzz", True, [], id="no-match"),
        pytest.param("heightened", True, ["Auspex"], id="synonym"),
        pytest.param("heightened", False, [], id="synonyms-off"),
        pytest.param("monster", True, ["Beast"], id="synonym-case-insensitive"),
        pytest.param("aus", True, ["Auspex"], id="name-and-synonym-once"),
    ],
)
def test_search(
    app, mock_cache_store, fake_vclient, query: str, expected: list[str], *, include_synonyms: bool
) -> None:
    """Verify search matches names, and synonyms when asked, by case-insensitive substring."""
    fake_vclient.set_response(
        Routes.DICTIONARY_LIST,
        items=[DictionaryTermFactory.build(term=n, synonyms=s) for n, s in _SEARCH_TERMS],
    )

    with app.test_request_context("/"):
        seed_session()
        result = search(query, include_synonyms=include_synonyms)

    assert [t.term for t in result] == expected
