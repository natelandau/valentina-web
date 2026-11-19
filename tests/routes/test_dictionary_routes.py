"""Tests for dictionary browsing and CRUD routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf, htmx_delete, htmx_post
from vweb.api_client.testing import (
    DictionaryTermFactory,
    Routes,
    TraitFactory,
    TraitSubcategoryFactory,
)
from vweb.routes.dictionary.services import validate_term

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from pytest_mock import MockerFixture


VALID_FORM = {"term": "Auspex", "definition": "A discipline.", "link": "", "synonyms": "sight"}


@pytest.fixture
def mock_dict_cache(mocker: MockerFixture) -> dict:
    """Patch the dictionary cache lookups the routes read terms from."""
    return {
        "terms": mocker.patch("vweb.lib.cache.dictionary.terms", autospec=True, return_value=[]),
        "term": mocker.patch("vweb.lib.cache.dictionary.term", autospec=True),
        "search": mocker.patch("vweb.lib.cache.dictionary.search", autospec=True),
        "clear": mocker.patch("vweb.lib.cache.dictionary.clear", autospec=True),
    }


class TestDictionaryBrowse:
    """Tests for listing, searching, and viewing terms."""

    def test_index_lists_terms(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify the dictionary page lists every term."""
        terms = DictionaryTermFactory.batch(3)
        mock_dict_cache["terms"].return_value = terms

        response = client.get("/dictionary")

        assert response.status_code == 200
        for term in terms:
            assert term.term.encode() in response.data

    @pytest.mark.parametrize(
        ("query", "expected_search", "expected_synonyms"),
        [
            ("?search=aus", "aus", False),
            ("?search=%20%20", "", False),
            ("", "", False),
            ("?search=heightened&include_synonyms=on", "heightened", True),
        ],
        ids=["query", "whitespace-only", "no-param", "with-synonyms"],
    )
    def test_search_lists_matching_terms(
        self,
        client: FlaskClient,
        mock_dict_cache: dict,
        query,
        expected_search,
        expected_synonyms,
    ) -> None:
        """Verify search sends the stripped query and synonym toggle, and lists the matches."""
        matches = DictionaryTermFactory.batch(2)
        mock_dict_cache["search"].return_value = matches

        response = client.get(f"/dictionary/search{query}")

        assert response.status_code == 200
        mock_dict_cache["search"].assert_called_once_with(
            expected_search, include_synonyms=expected_synonyms
        )
        for term in matches:
            assert term.term.encode() in response.data

    def test_direct_request_renders_term_within_full_list(
        self, client: FlaskClient, mock_dict_cache: dict
    ) -> None:
        """Verify direct navigation to a term renders the whole dictionary with the term open."""
        term = DictionaryTermFactory.build(id="t1", term="Auspex", source_type=None)
        other = DictionaryTermFactory.build(term="Obfuscate")
        mock_dict_cache["term"].return_value = term
        mock_dict_cache["terms"].return_value = [term, other]

        response = client.get("/dictionary/term/t1")

        assert response.status_code == 200
        assert b"Auspex" in response.data
        assert b"Obfuscate" in response.data

    def test_link_only_term_shows_link(self, client: FlaskClient, mock_dict_cache: dict) -> None:
        """Verify a term with only a link shows that link."""
        mock_dict_cache["term"].return_value = DictionaryTermFactory.build(
            id="t1", definition=None, link="https://example.com", source_type=None
        )

        response = client.get("/dictionary/term/t1", headers={"HX-Request": "true"})

        assert b"https://example.com" in response.data

    @pytest.mark.parametrize(
        ("source_type", "lookup", "source"),
        [
            (
                "trait",
                "trait",
                TraitFactory.build(sheet_section_name="Zeta Section", category_name="Omega Group"),
            ),
            (
                "trait_subcategory",
                "subcategory",
                TraitSubcategoryFactory.build(
                    sheet_section_name="Zeta Section", category_name="Omega Group"
                ),
            ),
        ],
    )
    def test_sourced_term_shows_where_it_lives_on_the_sheet(
        self, client: FlaskClient, mock_dict_cache: dict, mocker, source_type, lookup, source
    ) -> None:
        """Verify a term generated from a trait or subcategory shows its sheet section and category."""
        # Given a term generated from a blueprint trait or subcategory
        mock_dict_cache["term"].return_value = DictionaryTermFactory.build(
            id="t1", source_type=source_type, source_id="src-1"
        )
        fetch = mocker.patch(f"vweb.lib.cache.blueprint.{lookup}", return_value=source)

        # When viewing the term
        response = client.get("/dictionary/term/t1", headers={"HX-Request": "true"})

        # Then the source is looked up and its place on the sheet is shown
        fetch.assert_called_once_with("src-1")
        body = response.get_data(as_text=True)
        assert "Zeta Section" in body
        assert "Omega Group" in body

    @pytest.mark.parametrize(
        ("source_type", "editable"), [(None, True), ("trait", False)], ids=["company", "sourced"]
    )
    def test_only_company_terms_offer_edit_and_delete(
        self, client: FlaskClient, mock_dict_cache: dict, mocker, source_type, editable
    ) -> None:
        """Verify edit and delete controls appear only for terms the company wrote."""
        mocker.patch("vweb.lib.cache.blueprint.trait", return_value=None)
        mock_dict_cache["term"].return_value = DictionaryTermFactory.build(
            id="t1", source_type=source_type, source_id="src-1"
        )

        body = client.get("/dictionary/term/t1", headers={"HX-Request": "true"}).get_data(
            as_text=True
        )

        assert ("/dictionary/term/form/t1" in body) is editable
        assert ('hx-delete="/dictionary/term/t1"' in body) is editable

    def test_empty_detail_placeholder_renders(self, client: FlaskClient) -> None:
        """Verify the empty detail panel endpoint responds."""
        response = client.get("/dictionary/term/empty", headers={"HX-Request": "true"})

        assert response.status_code == 200

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/dictionary/term/bad"),
            ("get", "/dictionary/term/form/bad"),
            ("post", "/dictionary/term/bad"),
            ("delete", "/dictionary/term/bad"),
        ],
    )
    def test_unknown_term_returns_404(
        self, client: FlaskClient, mock_dict_cache: dict, fake_vclient, method, path
    ) -> None:
        """Verify reading, editing, or deleting an unknown term returns 404 and changes nothing."""
        mock_dict_cache["term"].return_value = None

        response = getattr(client, method)(
            path,
            data={**VALID_FORM, "csrf_token": get_csrf(client)},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        assert response.status_code == 404
        fake_vclient.assert_not_called(Routes.DICTIONARY_UPDATE)
        fake_vclient.assert_not_called(Routes.DICTIONARY_DELETE)


class TestDictionaryForm:
    """Tests for the add and edit term form."""

    def test_add_form_posts_to_create(self, client: FlaskClient) -> None:
        """Verify the add form submits to the create endpoint."""
        response = client.get("/dictionary/term/form", headers={"HX-Request": "true"})

        assert 'hx-post="/dictionary/term"' in response.get_data(as_text=True)

    @pytest.mark.parametrize("htmx", [True, False], ids=["fragment", "full-page"])
    def test_edit_form_is_prefilled_and_posts_to_update(
        self, client: FlaskClient, mock_dict_cache: dict, htmx
    ) -> None:
        """Verify the edit form, as a fragment or a full mobile page, edits the stored term."""
        mock_dict_cache["term"].return_value = DictionaryTermFactory.build(
            id="t1", term="Auspex", definition="A discipline.", source_type=None
        )
        headers = {"HX-Request": "true"} if htmx else {}

        response = client.get("/dictionary/term/form/t1", headers=headers)

        body = response.get_data(as_text=True)
        assert "Auspex" in body
        assert 'hx-post="/dictionary/term/t1"' in body


class TestDictionaryMutations:
    """Tests for creating, updating, and deleting terms."""

    def test_create_sends_term_and_refreshes_list(
        self, client: FlaskClient, mock_dict_cache: dict, fake_vclient
    ) -> None:
        """Verify a new term reaches the API, the cache is cleared, and the term is shown."""
        created = DictionaryTermFactory.build(id="new-1", term="Auspex", source_type=None)
        fake_vclient.set_response(Routes.DICTIONARY_CREATE, model=created)
        mock_dict_cache["terms"].return_value = [created]

        response = htmx_post(client, "/dictionary/term", VALID_FORM)

        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.DICTIONARY_CREATE,
            json={"term": "Auspex", "definition": "A discipline.", "synonyms": ["sight"]},
            times=1,
        )
        mock_dict_cache["clear"].assert_called_once()
        assert b"Auspex" in response.data

    def test_update_sends_term_and_clears_cache(
        self, client: FlaskClient, mock_dict_cache: dict, fake_vclient
    ) -> None:
        """Verify an edited term reaches the API and the cache is cleared."""
        term = DictionaryTermFactory.build(id="t1", source_type=None)
        mock_dict_cache["term"].return_value = term
        fake_vclient.set_response(Routes.DICTIONARY_UPDATE, model=term)

        response = htmx_post(client, "/dictionary/term/t1", VALID_FORM)

        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.DICTIONARY_UPDATE,
            params={"term_id": "t1"},
            json_subset={"term": "Auspex", "definition": "A discipline."},
            times=1,
        )
        mock_dict_cache["clear"].assert_called_once()

    def test_delete_sends_delete_and_clears_cache(
        self, client: FlaskClient, mock_dict_cache: dict, fake_vclient
    ) -> None:
        """Verify a deleted term is removed through the API and the cache is cleared."""
        mock_dict_cache["term"].return_value = DictionaryTermFactory.build(
            id="t1", source_type=None
        )

        response = htmx_delete(client, "/dictionary/term/t1")

        assert response.status_code == 200
        fake_vclient.assert_called(Routes.DICTIONARY_DELETE, params={"term_id": "t1"}, times=1)
        mock_dict_cache["clear"].assert_called_once()

    @pytest.mark.parametrize("path", ["/dictionary/term", "/dictionary/term/t1"])
    def test_invalid_form_rerenders_without_calling_api(
        self, client: FlaskClient, mock_dict_cache: dict, fake_vclient, path
    ) -> None:
        """Verify an invalid term shows its error and nothing reaches the API."""
        mock_dict_cache["term"].return_value = DictionaryTermFactory.build(
            id="t1", source_type=None
        )
        form = {**VALID_FORM, "term": "ab"}

        response = htmx_post(client, path, form)

        assert response.status_code == 200
        assert validate_term(form)["term"] in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.DICTIONARY_CREATE)
        fake_vclient.assert_not_called(Routes.DICTIONARY_UPDATE)

    @pytest.mark.parametrize(
        ("method", "route"),
        [("post", Routes.DICTIONARY_UPDATE), ("delete", Routes.DICTIONARY_DELETE)],
        ids=["update", "delete"],
    )
    def test_sourced_term_cannot_be_changed(
        self, client: FlaskClient, mock_dict_cache: dict, fake_vclient, method, route
    ) -> None:
        """Verify a term generated from the blueprint cannot be edited or deleted."""
        mock_dict_cache["term"].return_value = DictionaryTermFactory.build(
            id="t1", source_type="trait"
        )

        response = getattr(client, method)(
            "/dictionary/term/t1",
            data={**VALID_FORM, "csrf_token": get_csrf(client)},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        assert response.status_code == 403
        fake_vclient.assert_not_called(route)

    @pytest.fixture
    def editable_term(self, mock_dict_cache: dict) -> None:
        """Serve a company term that may be changed."""
        mock_dict_cache["term"].return_value = DictionaryTermFactory.build(
            id="t1", source_type=None
        )

    @pytest.mark.usefixtures("editable_term")
    @pytest.mark.parametrize(
        ("method", "path", "route", "status_code", "detail"),
        [
            ("post", "/dictionary/term", Routes.DICTIONARY_CREATE, 409, "Term exists"),
            ("delete", "/dictionary/term/t1", Routes.DICTIONARY_DELETE, 403, "Not yours"),
        ],
        ids=["create-conflict", "delete-refused"],
    )
    def test_fixable_refusal_shows_reason(  # noqa: PLR0917
        self, client: FlaskClient, fake_vclient, method, path, route, status_code, detail
    ) -> None:
        """Verify a refusal the user can act on shows the API's reason."""
        # Given an API that refuses the change
        fake_vclient.set_error(route, status_code=status_code, detail=detail)

        # When sending the change
        if method == "post":
            response = htmx_post(client, path, VALID_FORM)
        else:
            response = htmx_delete(client, path)

        # Then an error is shown with the API's reason
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'role="alert"' in body
        assert detail in body

    @pytest.mark.usefixtures("editable_term")
    def test_server_error_hides_detail(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a server error shows an error without the API's detail."""
        # Given an API that fails the update
        fake_vclient.set_error(Routes.DICTIONARY_UPDATE, status_code=500, detail="db exploded")

        # When sending the change
        response = htmx_post(client, "/dictionary/term/t1", VALID_FORM)

        # Then an error is shown without the server's detail
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'role="alert"' in body
        assert "db exploded" not in body
