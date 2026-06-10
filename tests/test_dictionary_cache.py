"""Tests for global dictionary term cache."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import DictionaryTermFactory

from tests.helpers import seed_session
from vweb.lib.cache.dictionary import (
    clear,
    search,
    term,
    terms,
)


@pytest.fixture
def mock_dict_svc(mocker):
    """Mock the sync_dictionary_service factory."""
    svc = MagicMock()
    mocker.patch("vweb.lib.cache.dictionary.sync_dictionary_service", return_value=svc)
    return svc


class TestTerms:
    """Tests for terms()."""

    def test_fetches_from_api_on_cache_miss(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify terms calls the API when the cache is empty."""
        # Given three terms returned by the API
        term_list = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.return_value = term_list

        # When fetching all terms
        with app.test_request_context("/"):
            seed_session()
            result = terms()

        # Then the result is a sorted list of 3 terms and the API was called once
        assert len(result) == 3
        assert result == sorted(result, key=lambda t: t.term.lower())
        mock_dict_svc.list_all.assert_called_once()

    def test_returns_cached_on_hit(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify terms returns cached list without calling the API again."""
        # Given terms are already cached from a first call
        term_list = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.return_value = term_list

        with app.test_request_context("/"):
            seed_session()
            first = terms()
            second = terms()

        # Then the API is called only once and both results are the same object
        assert first is second
        mock_dict_svc.list_all.assert_called_once()

    def test_returns_empty_list_when_no_terms(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify terms returns an empty list when the API returns no terms."""
        # Given the API returns an empty list
        mock_dict_svc.list_all.return_value = []

        # When fetching all terms
        with app.test_request_context("/"):
            seed_session()
            result = terms()

        # Then the result is an empty list
        assert result == []

    def test_terms_sorted_alphabetically(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify terms returns terms sorted alphabetically by term name."""
        # Given terms with specific names in non-alphabetical order
        term_list = [
            DictionaryTermFactory.build(term="Zephyr"),
            DictionaryTermFactory.build(term="Amaranth"),
            DictionaryTermFactory.build(term="Beast"),
        ]
        mock_dict_svc.list_all.return_value = term_list

        # When fetching all terms
        with app.test_request_context("/"):
            seed_session()
            result = terms()

        # Then the result is sorted alphabetically
        assert [t.term for t in result] == ["Amaranth", "Beast", "Zephyr"]


class TestTerm:
    """Tests for term()."""

    def test_returns_term_for_known_id(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify term returns the correct term for a known ID."""
        # Given a term exists in the cache
        t = DictionaryTermFactory.build(id="term-1", term="Amaranth")
        mock_dict_svc.list_all.return_value = [t]

        # When looking up by ID
        with app.test_request_context("/"):
            seed_session()
            result = term("term-1")

        # Then the term is returned
        assert result is t

    def test_returns_none_for_unknown_id(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify term returns None for an unknown term ID."""
        # Given the cache has terms but not the requested one
        mock_dict_svc.list_all.return_value = [DictionaryTermFactory.build(id="other")]

        # When looking up an unknown ID
        with app.test_request_context("/"):
            seed_session()
            result = term("nonexistent")

        # Then None is returned
        assert result is None


class TestClear:
    """Tests for clear()."""

    def test_forces_refetch_on_next_call(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify clear forces a fresh API fetch on next access."""
        # Given terms are cached
        terms_v1 = DictionaryTermFactory.batch(2)
        terms_v2 = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.side_effect = [terms_v1, terms_v2]

        with app.test_request_context("/"):
            seed_session()
            first = terms()
            assert len(first) == 2

            # When the cache is cleared
            clear()

            # Then the next call fetches fresh data
            second = terms()
            assert len(second) == 3

        assert mock_dict_svc.list_all.call_count == 2


class TestSearch:
    """Tests for search()."""

    def test_filters_by_substring_match(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search filters terms by substring match on term name."""
        # Given terms with specific names
        term_list = [
            DictionaryTermFactory.build(term="Amaranth"),
            DictionaryTermFactory.build(term="Auspex"),
            DictionaryTermFactory.build(term="Beast"),
        ]
        mock_dict_svc.list_all.return_value = term_list

        # When searching for a substring
        with app.test_request_context("/"):
            seed_session()
            result = search("aus")

        # Then only matching terms are returned
        assert len(result) == 1
        assert result[0].term == "Auspex"

    def test_case_insensitive_search(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search performs case-insensitive matching."""
        # Given a term with mixed case
        t = DictionaryTermFactory.build(term="Auspex")
        mock_dict_svc.list_all.return_value = [t]

        # When searching with uppercase
        with app.test_request_context("/"):
            seed_session()
            result = search("AUS")

        # Then the term is found
        assert len(result) == 1
        assert result[0].term == "Auspex"

    def test_empty_query_returns_all(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search returns all terms when query is empty."""
        # Given three terms
        term_list = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.return_value = term_list

        # When searching with empty string
        with app.test_request_context("/"):
            seed_session()
            result = search("")

        # Then all terms are returned
        assert len(result) == 3

    def test_no_matches_returns_empty(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search returns empty list when no terms match."""
        # Given terms that don't match the query
        term_list = [
            DictionaryTermFactory.build(term="Amaranth"),
            DictionaryTermFactory.build(term="Beast"),
        ]
        mock_dict_svc.list_all.return_value = term_list

        # When searching for a non-matching string
        with app.test_request_context("/"):
            seed_session()
            result = search("zzz")

        # Then an empty list is returned
        assert result == []


class TestSearchSynonyms:
    """Tests for search() synonym matching."""

    def test_synonym_match_returns_term(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search matches against synonyms when include_synonyms is True."""
        # Given a term with a synonym that matches the query but term name does not
        term_list = [
            DictionaryTermFactory.build(term="Auspex", synonyms=["heightened senses"]),
            DictionaryTermFactory.build(term="Beast", synonyms=[]),
        ]
        mock_dict_svc.list_all.return_value = term_list

        # When searching for the synonym text
        with app.test_request_context("/"):
            seed_session()
            result = search("heightened", include_synonyms=True)

        # Then the parent term is returned
        assert len(result) == 1
        assert result[0].term == "Auspex"

    def test_synonym_match_excluded_when_disabled(
        self, app, mock_cache_store, mock_dict_svc
    ) -> None:
        """Verify synonym matches are excluded when include_synonyms is False."""
        # Given a term with a synonym
        term_list = [
            DictionaryTermFactory.build(term="Auspex", synonyms=["heightened senses"]),
        ]
        mock_dict_svc.list_all.return_value = term_list

        # When searching with synonyms disabled
        with app.test_request_context("/"):
            seed_session()
            result = search("heightened", include_synonyms=False)

        # Then no results are returned
        assert result == []

    def test_term_name_match_ignores_synonym_flag(
        self, app, mock_cache_store, mock_dict_svc
    ) -> None:
        """Verify term name match works regardless of include_synonyms value."""
        # Given a term whose name matches the query
        term_list = [DictionaryTermFactory.build(term="Auspex", synonyms=["heightened senses"])]
        mock_dict_svc.list_all.return_value = term_list

        # When searching with synonyms disabled
        with app.test_request_context("/"):
            seed_session()
            result = search("aus", include_synonyms=False)

        # Then the term is still found by name
        assert len(result) == 1
        assert result[0].term == "Auspex"

    def test_empty_query_returns_all_regardless_of_flag(
        self, app, mock_cache_store, mock_dict_svc
    ) -> None:
        """Verify empty query returns all terms regardless of include_synonyms."""
        # Given three terms
        term_list = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.return_value = term_list

        # When searching with empty query and synonyms disabled
        with app.test_request_context("/"):
            seed_session()
            result = search("", include_synonyms=False)

        # Then all terms are returned
        assert len(result) == 3

    def test_no_duplicate_when_both_name_and_synonym_match(
        self, app, mock_cache_store, mock_dict_svc
    ) -> None:
        """Verify a term appears only once when both name and synonym match."""
        # Given a term whose name and a synonym both contain the query
        term_list = [DictionaryTermFactory.build(term="Aus", synonyms=["aus-pex"])]
        mock_dict_svc.list_all.return_value = term_list

        # When searching
        with app.test_request_context("/"):
            seed_session()
            result = search("aus", include_synonyms=True)

        # Then the term appears exactly once
        assert len(result) == 1

    def test_synonym_match_is_case_insensitive(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify synonym matching is case-insensitive."""
        # Given a term with an uppercase synonym
        term_list = [DictionaryTermFactory.build(term="Beast", synonyms=["The Monster"])]
        mock_dict_svc.list_all.return_value = term_list

        # When searching with lowercase
        with app.test_request_context("/"):
            seed_session()
            result = search("monster", include_synonyms=True)

        # Then the term is found
        assert len(result) == 1
        assert result[0].term == "Beast"
