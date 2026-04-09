"""Tests for global dictionary term cache."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import DictionaryTermFactory

from tests.helpers import make_cache_store_mock
from vweb.routes.dictionary.cache import (
    clear_dictionary_cache,
    get_all_terms,
    get_term,
    search_terms,
)


@pytest.fixture
def mock_cache_store(mocker) -> dict:
    """Provide a dict-backed cache mock for dictionary_cache."""
    return make_cache_store_mock(mocker, "vweb.routes.dictionary.cache.cache")


@pytest.fixture
def mock_dict_svc(mocker):
    """Mock the sync_dictionary_service factory."""
    svc = MagicMock()
    mocker.patch("vweb.routes.dictionary.cache.sync_dictionary_service", return_value=svc)
    return svc


class TestGetAllTerms:
    """Tests for get_all_terms()."""

    def test_fetches_from_api_on_cache_miss(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify get_all_terms calls the API when the cache is empty."""
        # Given three terms returned by the API
        terms = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.return_value = terms

        # When fetching all terms
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = get_all_terms()

        # Then the result is a sorted list of 3 terms and the API was called once
        assert len(result) == 3
        assert result == sorted(result, key=lambda t: t.term.lower())
        mock_dict_svc.list_all.assert_called_once()

    def test_returns_cached_on_hit(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify get_all_terms returns cached list without calling the API again."""
        # Given terms are already cached from a first call
        terms = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.return_value = terms

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            first = get_all_terms()
            second = get_all_terms()

        # Then the API is called only once and both results are the same object
        assert first is second
        mock_dict_svc.list_all.assert_called_once()

    def test_returns_empty_list_when_no_terms(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify get_all_terms returns an empty list when the API returns no terms."""
        # Given the API returns an empty list
        mock_dict_svc.list_all.return_value = []

        # When fetching all terms
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = get_all_terms()

        # Then the result is an empty list
        assert result == []

    def test_terms_sorted_alphabetically(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify get_all_terms returns terms sorted alphabetically by term name."""
        # Given terms with specific names in non-alphabetical order
        terms = [
            DictionaryTermFactory.build(term="Zephyr"),
            DictionaryTermFactory.build(term="Amaranth"),
            DictionaryTermFactory.build(term="Beast"),
        ]
        mock_dict_svc.list_all.return_value = terms

        # When fetching all terms
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = get_all_terms()

        # Then the result is sorted alphabetically
        assert [t.term for t in result] == ["Amaranth", "Beast", "Zephyr"]


class TestGetTerm:
    """Tests for get_term()."""

    def test_returns_term_for_known_id(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify get_term returns the correct term for a known ID."""
        # Given a term exists in the cache
        term = DictionaryTermFactory.build(id="term-1", term="Amaranth")
        mock_dict_svc.list_all.return_value = [term]

        # When looking up by ID
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = get_term("term-1")

        # Then the term is returned
        assert result is term

    def test_returns_none_for_unknown_id(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify get_term returns None for an unknown term ID."""
        # Given the cache has terms but not the requested one
        mock_dict_svc.list_all.return_value = [DictionaryTermFactory.build(id="other")]

        # When looking up an unknown ID
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = get_term("nonexistent")

        # Then None is returned
        assert result is None


class TestClearDictionaryCache:
    """Tests for clear_dictionary_cache()."""

    def test_forces_refetch_on_next_call(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify clear_dictionary_cache forces a fresh API fetch on next access."""
        # Given terms are cached
        terms_v1 = DictionaryTermFactory.batch(2)
        terms_v2 = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.side_effect = [terms_v1, terms_v2]

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            first = get_all_terms()
            assert len(first) == 2

            # When the cache is cleared
            clear_dictionary_cache()

            # Then the next call fetches fresh data
            second = get_all_terms()
            assert len(second) == 3

        assert mock_dict_svc.list_all.call_count == 2


class TestSearchTerms:
    """Tests for search_terms()."""

    def test_filters_by_substring_match(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search_terms filters terms by substring match on term name."""
        # Given terms with specific names
        terms = [
            DictionaryTermFactory.build(term="Amaranth"),
            DictionaryTermFactory.build(term="Auspex"),
            DictionaryTermFactory.build(term="Beast"),
        ]
        mock_dict_svc.list_all.return_value = terms

        # When searching for a substring
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("aus")

        # Then only matching terms are returned
        assert len(result) == 1
        assert result[0].term == "Auspex"

    def test_case_insensitive_search(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search_terms performs case-insensitive matching."""
        # Given a term with mixed case
        term = DictionaryTermFactory.build(term="Auspex")
        mock_dict_svc.list_all.return_value = [term]

        # When searching with uppercase
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("AUS")

        # Then the term is found
        assert len(result) == 1
        assert result[0].term == "Auspex"

    def test_empty_query_returns_all(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search_terms returns all terms when query is empty."""
        # Given three terms
        terms = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.return_value = terms

        # When searching with empty string
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("")

        # Then all terms are returned
        assert len(result) == 3

    def test_no_matches_returns_empty(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search_terms returns empty list when no terms match."""
        # Given terms that don't match the query
        terms = [
            DictionaryTermFactory.build(term="Amaranth"),
            DictionaryTermFactory.build(term="Beast"),
        ]
        mock_dict_svc.list_all.return_value = terms

        # When searching for a non-matching string
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("zzz")

        # Then an empty list is returned
        assert result == []


class TestSearchTermsSynonyms:
    """Tests for search_terms() synonym matching."""

    def test_synonym_match_returns_term(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify search matches against synonyms when include_synonyms is True."""
        # Given a term with a synonym that matches the query but term name does not
        terms = [
            DictionaryTermFactory.build(term="Auspex", synonyms=["heightened senses"]),
            DictionaryTermFactory.build(term="Beast", synonyms=[]),
        ]
        mock_dict_svc.list_all.return_value = terms

        # When searching for the synonym text
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("heightened", include_synonyms=True)

        # Then the parent term is returned
        assert len(result) == 1
        assert result[0].term == "Auspex"

    def test_synonym_match_excluded_when_disabled(
        self, app, mock_cache_store, mock_dict_svc
    ) -> None:
        """Verify synonym matches are excluded when include_synonyms is False."""
        # Given a term with a synonym
        terms = [
            DictionaryTermFactory.build(term="Auspex", synonyms=["heightened senses"]),
        ]
        mock_dict_svc.list_all.return_value = terms

        # When searching with synonyms disabled
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("heightened", include_synonyms=False)

        # Then no results are returned
        assert result == []

    def test_term_name_match_ignores_synonym_flag(
        self, app, mock_cache_store, mock_dict_svc
    ) -> None:
        """Verify term name match works regardless of include_synonyms value."""
        # Given a term whose name matches the query
        terms = [DictionaryTermFactory.build(term="Auspex", synonyms=["heightened senses"])]
        mock_dict_svc.list_all.return_value = terms

        # When searching with synonyms disabled
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("aus", include_synonyms=False)

        # Then the term is still found by name
        assert len(result) == 1
        assert result[0].term == "Auspex"

    def test_empty_query_returns_all_regardless_of_flag(
        self, app, mock_cache_store, mock_dict_svc
    ) -> None:
        """Verify empty query returns all terms regardless of include_synonyms."""
        # Given three terms
        terms = DictionaryTermFactory.batch(3)
        mock_dict_svc.list_all.return_value = terms

        # When searching with empty query and synonyms disabled
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("", include_synonyms=False)

        # Then all terms are returned
        assert len(result) == 3

    def test_no_duplicate_when_both_name_and_synonym_match(
        self, app, mock_cache_store, mock_dict_svc
    ) -> None:
        """Verify a term appears only once when both name and synonym match."""
        # Given a term whose name and a synonym both contain the query
        terms = [DictionaryTermFactory.build(term="Aus", synonyms=["aus-pex"])]
        mock_dict_svc.list_all.return_value = terms

        # When searching
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("aus", include_synonyms=True)

        # Then the term appears exactly once
        assert len(result) == 1

    def test_synonym_match_is_case_insensitive(self, app, mock_cache_store, mock_dict_svc) -> None:
        """Verify synonym matching is case-insensitive."""
        # Given a term with an uppercase synonym
        terms = [DictionaryTermFactory.build(term="Beast", synonyms=["The Monster"])]
        mock_dict_svc.list_all.return_value = terms

        # When searching with lowercase
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result = search_terms("monster", include_synonyms=True)

        # Then the term is found
        assert len(result) == 1
        assert result[0].term == "Beast"
