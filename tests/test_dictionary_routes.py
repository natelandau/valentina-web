"""Tests for dictionary browsing and CRUD routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.exceptions import APIError
from vclient.testing import DictionaryTermFactory

from tests.conftest import get_csrf

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from pytest_mock import MockerFixture


@pytest.fixture
def mock_dict_cache(mocker: MockerFixture) -> dict:
    """Patch dictionary cache functions used by the dictionary routes."""
    mocks: dict = {}
    mocks["get_all_terms"] = mocker.patch(
        "vweb.routes.dictionary.views.get_all_terms", autospec=True
    )
    mocks["get_term"] = mocker.patch("vweb.routes.dictionary.views.get_term", autospec=True)
    mocks["search_terms"] = mocker.patch("vweb.routes.dictionary.views.search_terms", autospec=True)
    return mocks


class TestDictionaryIndex:
    """Tests for GET /dictionary."""

    def test_renders_dictionary_page(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify dictionary index renders with terms."""
        # Given three dictionary terms
        mock_dict_cache["get_all_terms"].return_value = DictionaryTermFactory.batch(3)

        # When requesting the dictionary page
        response = client.get("/dictionary")

        # Then the page renders successfully
        assert response.status_code == 200
        assert b"Dictionary" in response.data

    def test_renders_empty_state(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify dictionary index shows empty state when no terms exist."""
        # Given no dictionary terms
        mock_dict_cache["get_all_terms"].return_value = []

        # When requesting the dictionary page
        response = client.get("/dictionary")

        # Then the page renders with the empty message
        assert response.status_code == 200
        assert b"No terms found" in response.data


class TestDictionarySearch:
    """Tests for GET /dictionary/search."""

    def test_returns_filtered_term_list(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify search returns filtered results matching the query."""
        # Given a search that matches one term
        term = DictionaryTermFactory.build(term="Auspex")
        mock_dict_cache["search_terms"].return_value = [term]

        # When searching for "aus"
        response = client.get("/dictionary/search?search=aus")

        # Then the matching term is returned
        assert response.status_code == 200
        assert b"Auspex" in response.data

    def test_empty_search_returns_all(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify empty search query returns all terms."""
        # Given three terms returned for empty search
        terms = DictionaryTermFactory.batch(3)
        mock_dict_cache["search_terms"].return_value = terms

        # When searching with an empty string
        response = client.get("/dictionary/search?search=")

        # Then all term names appear in the response
        assert response.status_code == 200
        for term in terms:
            assert term.term.encode() in response.data


class TestTermDetail:
    """Tests for GET /dictionary/term/<term_id>."""

    def test_direct_request_returns_full_page(
        self, client: FlaskClient, mock_dict_cache: dict
    ) -> None:
        """Verify direct navigation returns a full page with back link."""
        # Given a term
        term = DictionaryTermFactory.build(id="t1", term="Auspex")
        mock_dict_cache["get_term"].return_value = term

        # When requesting without HTMX header
        response = client.get("/dictionary/term/t1")

        # Then a full page is returned with the term name and back link
        assert response.status_code == 200
        assert b"Auspex" in response.data
        assert b"Back to Dictionary" in response.data

    def test_unknown_term_returns_404(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify unknown term ID returns 404."""
        # Given the term is not found
        mock_dict_cache["get_term"].return_value = None

        # When requesting an unknown term
        response = client.get("/dictionary/term/bad")

        # Then a 404 is returned
        assert response.status_code == 404


class TestDictionarySearchEdgeCases:
    """Tests for dictionary search edge cases."""

    def test_search_with_whitespace_only(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify whitespace-only search is stripped and returns all terms."""
        # Given search_terms returns all terms when called with empty string
        terms = DictionaryTermFactory.batch(3)
        mock_dict_cache["search_terms"].return_value = terms

        # When searching with whitespace-only query
        response = client.get("/dictionary/search?search=%20%20")

        # Then all terms are returned
        assert response.status_code == 200
        mock_dict_cache["search_terms"].assert_called_once_with("", include_synonyms=False)
        for term in terms:
            assert term.term.encode() in response.data

    def test_search_without_param(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify missing search param defaults to empty string and returns all terms."""
        # Given search_terms returns all terms
        terms = DictionaryTermFactory.batch(3)
        mock_dict_cache["search_terms"].return_value = terms

        # When searching without a search parameter
        response = client.get("/dictionary/search")

        # Then all terms are returned
        assert response.status_code == 200
        mock_dict_cache["search_terms"].assert_called_once_with("", include_synonyms=False)
        for term in terms:
            assert term.term.encode() in response.data


class TestDictionarySearchSynonymToggle:
    """Tests for include_synonyms query param on search endpoint."""

    def test_search_with_synonyms_on(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify search passes include_synonyms=True when checkbox is checked."""
        # Given search returns results
        term = DictionaryTermFactory.build(term="Auspex")
        mock_dict_cache["search_terms"].return_value = [term]

        # When searching with include_synonyms=on
        response = client.get("/dictionary/search?search=heightened&include_synonyms=on")

        # Then search_terms is called with include_synonyms=True
        assert response.status_code == 200
        mock_dict_cache["search_terms"].assert_called_once_with("heightened", include_synonyms=True)

    def test_search_without_synonyms_param(
        self, client: FlaskClient, mock_dict_cache: dict
    ) -> None:
        """Verify search passes include_synonyms=False when checkbox param is absent."""
        # Given search returns no results
        mock_dict_cache["search_terms"].return_value = []

        # When searching without the include_synonyms param
        response = client.get("/dictionary/search?search=heightened")

        # Then search_terms is called with include_synonyms=False
        assert response.status_code == 200
        mock_dict_cache["search_terms"].assert_called_once_with(
            "heightened", include_synonyms=False
        )


class TestTermDetailLinkOnly:
    """Tests for term detail with link-only terms."""

    def test_link_only_term_detail_htmx(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify link-only term detail includes the external link URL."""
        # Given a term with no definition but a link
        term = DictionaryTermFactory.build(
            id="link-term", term="Anarch", definition=None, link="https://example.com"
        )
        mock_dict_cache["get_term"].return_value = term

        # When requesting via HTMX
        response = client.get("/dictionary/term/link-term", headers={"HX-Request": "true"})

        # Then the response contains the link URL
        assert response.status_code == 200
        assert b"https://example.com" in response.data


class TestTermEmpty:
    """Tests for GET /dictionary/term/empty."""

    def test_returns_placeholder(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify the empty detail endpoint returns the placeholder fragment."""
        # When requesting the empty detail endpoint
        response = client.get("/dictionary/term/empty", headers={"HX-Request": "true"})

        # Then the placeholder is returned
        assert response.status_code == 200
        assert b"Select a term" in response.data


class TestDictionaryForm:
    """Tests for GET /dictionary/term/form."""

    def test_add_form_returns_empty_form(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify add form renders without pre-filled values."""
        # Given no specific term
        mock_dict_cache["get_all_terms"].return_value = []

        # When requesting the add form via HTMX
        response = client.get("/dictionary/term/form", headers={"HX-Request": "true"})

        # Then the form renders with "Add Term" heading
        assert response.status_code == 200
        assert b"Add Term" in response.data

    def test_edit_form_returns_prefilled(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify edit form is pre-filled with existing term data."""
        # Given an existing term
        term = DictionaryTermFactory.build(
            id="t1", term="Auspex", definition="A discipline.", is_global=False
        )
        mock_dict_cache["get_term"].return_value = term

        # When requesting the edit form via HTMX
        response = client.get("/dictionary/term/form/t1", headers={"HX-Request": "true"})

        # Then the form is pre-filled
        assert response.status_code == 200
        assert b"Edit Term" in response.data
        assert b"Auspex" in response.data

    def test_edit_form_unknown_term_returns_404(
        self, client: FlaskClient, mock_dict_cache: dict
    ) -> None:
        """Verify edit form for unknown term returns 404."""
        # Given the term is not found
        mock_dict_cache["get_term"].return_value = None

        # When requesting the edit form
        response = client.get("/dictionary/term/form/bad", headers={"HX-Request": "true"})

        # Then 404 is returned
        assert response.status_code == 404


class TestDictionaryCreate:
    """Tests for POST /dictionary/term."""

    def test_creates_term_and_returns_detail(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify successful creation returns updated term list and detail."""
        # Given the service creates successfully
        created = DictionaryTermFactory.build(id="new-1", term="Auspex")
        mock_create = mocker.patch(
            "vweb.routes.dictionary.views.svc_create_term", return_value=created
        )
        mock_clear = mocker.patch("vweb.routes.dictionary.views.clear_dictionary_cache")
        mock_dict_cache["get_all_terms"].return_value = [created]

        # When submitting the create form
        csrf = get_csrf(client)
        response = client.post(
            "/dictionary/term",
            data={
                "term": "Auspex",
                "definition": "A discipline.",
                "link": "",
                "synonyms": "",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then creation succeeds with 200
        assert response.status_code == 200
        mock_create.assert_called_once()
        mock_clear.assert_called_once()
        assert b"Auspex" in response.data

    def test_validation_errors_return_form(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify validation errors re-render the form with error messages."""
        # Given validation will fail (term too short)
        mock_dict_cache["get_all_terms"].return_value = []

        # When submitting with a too-short term
        csrf = get_csrf(client)
        response = client.post(
            "/dictionary/term",
            data={"term": "ab", "definition": "", "link": "", "synonyms": "", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the form is re-rendered with errors
        assert response.status_code == 200
        assert b"at least 3" in response.data

    def test_api_error_returns_form_with_error(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify API errors re-render the form with a generic error message."""
        # Given the API raises an error
        mocker.patch(
            "vweb.routes.dictionary.views.svc_create_term", side_effect=APIError("Server error")
        )
        mock_dict_cache["get_all_terms"].return_value = []

        # When submitting valid data that triggers an API error
        csrf = get_csrf(client)
        response = client.post(
            "/dictionary/term",
            data={
                "term": "Auspex",
                "definition": "",
                "link": "",
                "synonyms": "",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then the form is re-rendered with an error message
        assert response.status_code == 200
        assert b"error" in response.data.lower()


class TestDictionaryUpdate:
    """Tests for POST /dictionary/term/<term_id>."""

    def test_updates_term(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify successful update returns updated content."""
        # Given an existing non-global term
        term = DictionaryTermFactory.build(id="t1", term="Auspex")
        updated = DictionaryTermFactory.build(id="t1", term="Auspex Updated")
        mock_dict_cache["get_term"].return_value = term
        mock_update = mocker.patch(
            "vweb.routes.dictionary.views.svc_update_term", return_value=updated
        )
        mock_clear = mocker.patch("vweb.routes.dictionary.views.clear_dictionary_cache")
        mock_dict_cache["get_all_terms"].return_value = [updated]

        # When submitting the update form
        csrf = get_csrf(client)
        response = client.post(
            "/dictionary/term/t1",
            data={
                "term": "Auspex Updated",
                "definition": "",
                "link": "",
                "synonyms": "",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then update succeeds
        assert response.status_code == 200
        mock_update.assert_called_once()
        mock_clear.assert_called_once()

    def test_global_term_returns_403(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify updating a global term returns 403."""
        # Given a global term
        term = DictionaryTermFactory.build(id="t1", source_type="trait")
        mock_dict_cache["get_term"].return_value = term

        # When attempting to update
        csrf = get_csrf(client)
        response = client.post(
            "/dictionary/term/t1",
            data={
                "term": "Changed",
                "definition": "",
                "link": "",
                "synonyms": "",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then 403 is returned
        assert response.status_code == 403

    def test_validation_errors_return_form(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify validation errors re-render the form with the term pre-populated."""
        # Given an existing non-global term
        term = DictionaryTermFactory.build(id="t1", term="Auspex")
        mock_dict_cache["get_term"].return_value = term

        # When submitting with a too-short term name
        csrf = get_csrf(client)
        response = client.post(
            "/dictionary/term/t1",
            data={"term": "ab", "definition": "", "link": "", "synonyms": "", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the form is re-rendered with errors
        assert response.status_code == 200
        assert b"at least 3" in response.data

    def test_api_error_returns_form_with_error(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify API errors re-render the form with a generic error message."""
        # Given an existing non-global term and the API raises an error
        term = DictionaryTermFactory.build(id="t1", term="Auspex")
        mock_dict_cache["get_term"].return_value = term
        mocker.patch(
            "vweb.routes.dictionary.views.svc_update_term", side_effect=APIError("Server error")
        )

        # When submitting valid data that triggers an API error
        csrf = get_csrf(client)
        response = client.post(
            "/dictionary/term/t1",
            data={
                "term": "Auspex",
                "definition": "",
                "link": "",
                "synonyms": "",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then the form is re-rendered with an error message
        assert response.status_code == 200
        assert b"error" in response.data.lower()


class TestDictionaryDelete:
    """Tests for DELETE /dictionary/term/<term_id>."""

    def test_deletes_term(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify successful delete returns updated list and empty detail."""
        # Given an existing non-global term
        term = DictionaryTermFactory.build(id="t1")
        mock_dict_cache["get_term"].return_value = term
        mock_delete = mocker.patch("vweb.routes.dictionary.views.svc_delete_term")
        mock_clear = mocker.patch("vweb.routes.dictionary.views.clear_dictionary_cache")
        mock_dict_cache["get_all_terms"].return_value = []

        # When deleting via HTMX
        csrf = get_csrf(client)
        response = client.delete(
            "/dictionary/term/t1",
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then delete succeeds
        assert response.status_code == 200
        mock_delete.assert_called_once_with("t1")
        mock_clear.assert_called_once()
        assert b"Select a term" in response.data

    def test_global_term_returns_403(
        self, client: FlaskClient, mock_dict_cache: dict, mocker: MockerFixture
    ) -> None:
        """Verify deleting a global term returns 403."""
        # Given a global term
        term = DictionaryTermFactory.build(id="t1", source_type="trait")
        mock_dict_cache["get_term"].return_value = term

        # When attempting to delete
        csrf = get_csrf(client)
        response = client.delete(
            "/dictionary/term/t1",
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then 403 is returned
        assert response.status_code == 403


class TestGlobalTermRendering:
    """Tests for global term display behavior."""

    def test_company_term_detail_has_edit_delete(
        self, client: FlaskClient, mock_dict_cache: dict
    ) -> None:
        """Verify company term detail includes edit and delete buttons."""
        # Given a company-scoped term
        term = DictionaryTermFactory.build(id="t1", term="Auspex")
        mock_dict_cache["get_term"].return_value = term

        # When requesting the detail via HTMX
        response = client.get("/dictionary/term/t1", headers={"HX-Request": "true"})

        # Then edit/delete buttons are present
        assert response.status_code == 200
        assert b"Edit" in response.data
        assert b"Delete" in response.data
