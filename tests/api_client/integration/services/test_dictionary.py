"""Integration tests for DictionaryService."""

import json

import pytest
import respx

from tests.api_client.payloads import page
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import NotFoundError
from vweb.api_client.models import DictionaryTerm, PaginatedResponse


@pytest.fixture
def dictionary_term_response_data() -> dict:
    """Return sample dictionary term response data."""
    return {
        "id": "term123",
        "term": "Test Term",
        "definition": "A test definition",
        "link": "https://example.com",
        "synonyms": ["Test Synonym", "Test Synonym 2"],
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
    }


@pytest.fixture
def paginated_dictionary_terms_response(dictionary_term_response_data) -> dict:
    """Return a one-item paginated dictionary terms response."""
    return page(dictionary_term_response_data)


class TestDictionaryServiceGetPage:
    """Tests for DictionaryService.get_page method."""

    @respx.mock
    def test_get_page(self, vclient, base_url, paginated_dictionary_terms_response):
        """Verify getting a page of dictionary terms."""
        # Given: A mocked dictionary endpoint
        company_id = "company123"
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERMS.format(company_id=company_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_dictionary_terms_response)

        # When: Getting a page of dictionary terms
        result = vclient.dictionary("on-behalf-of-user", company_id=company_id).get_page()

        # Then: Returns paginated DictionaryTerm objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], DictionaryTerm)
        assert result.items[0].term == "Test Term"
        assert result.total == 1

    @respx.mock
    def test_get_page_with_filters(self, vclient, base_url, paginated_dictionary_terms_response):
        """Verify get_page accepts filter parameters."""
        # Given: A mocked endpoint expecting filter params
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERMS.format(company_id='company123')}",
            params={"limit": "10", "offset": "0", "term": "Test Term"},
        ).respond(200, json=paginated_dictionary_terms_response)

        # When: Getting a page of dictionary terms with filters
        result = vclient.dictionary("on-behalf-of-user", company_id="company123").get_page(
            term="Test Term"
        )

        # Then: Request was made with correct params
        assert route.called
        assert result.limit == 10
        assert result.offset == 0
        assert result.total == 1
        assert len(result.items) == 1
        assert isinstance(result.items[0], DictionaryTerm)
        assert result.items[0].term == "Test Term"

    @respx.mock
    def test_get_page_with_pagination(self, vclient, base_url, paginated_dictionary_terms_response):
        """Verify get_page accepts pagination parameters."""
        # Given: A mocked endpoint expecting pagination params
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERMS.format(company_id='company123')}",
            params={"limit": "25", "offset": "50"},
        ).respond(200, json=paginated_dictionary_terms_response)

        # When: Getting a page of dictionary terms with pagination
        result = vclient.dictionary("on-behalf-of-user", company_id="company123").get_page(
            limit=25, offset=50
        )

        # Then: Request was made with correct params
        assert route.called
        assert result.limit == 10
        assert result.offset == 0
        assert result.total == 1
        assert len(result.items) == 1
        assert isinstance(result.items[0], DictionaryTerm)
        assert result.items[0].term == "Test Term"

    @respx.mock
    def test_get_page_allows_reference_limit(
        self, vclient, base_url, paginated_dictionary_terms_response
    ):
        """Verify the dictionary accepts a limit up to 1000 without clamping to 100."""
        # Given: An endpoint expecting the reference max limit (1000)
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERMS.format(company_id='company123')}",
            params={"limit": "1000", "offset": "0"},
        ).respond(200, json=paginated_dictionary_terms_response)

        # When: Requesting a page with limit=1000
        vclient.dictionary("on-behalf-of-user", company_id="company123").get_page(limit=1000)

        # Then: The request used limit=1000 rather than the 100 cap
        assert route.called


class TestDictionaryServiceListAll:
    """Tests for DictionaryService.list_all method."""

    @respx.mock
    def test_list_all(self, vclient, base_url, paginated_dictionary_terms_response):
        """Verify listing all dictionary terms."""
        # Given: A mocked dictionary endpoint
        company_id = "company123"
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERMS.format(company_id=company_id)}",
        ).respond(200, json=paginated_dictionary_terms_response)

        # When: Listing all dictionary terms
        result = vclient.dictionary("on-behalf-of-user", company_id="company123").list_all()

        # Then: Returns list of DictionaryTerm objects
        assert route.called
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], DictionaryTerm)
        assert result[0].term == "Test Term"

    @respx.mock
    def test_list_all_with_filter(self, vclient, base_url, paginated_dictionary_terms_response):
        """Verify list_all accepts filter parameters."""
        # Given: A mocked endpoint expecting filter params
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERMS.format(company_id='company123')}",
            params={"limit": "1000", "offset": "0", "term": "Test"},
        ).respond(200, json=paginated_dictionary_terms_response)

        # When: Listing all dictionary terms with filters
        result = vclient.dictionary("on-behalf-of-user", company_id="company123").list_all(
            term="Test"
        )

        # Then: Request was made with correct params
        assert route.called
        assert len(result) == 1
        assert isinstance(result[0], DictionaryTerm)
        assert result[0].term == "Test Term"


class TestDictionaryServiceIterAll:
    """Tests for DictionaryService.iter_all method."""

    @respx.mock
    def test_iter_all(self, vclient, base_url, paginated_dictionary_terms_response):
        """Verify iter_all yields dictionary terms."""
        # Given: A mocked dictionary endpoint
        company_id = "company123"
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERMS.format(company_id=company_id)}",
        ).respond(200, json=paginated_dictionary_terms_response)

        # When: Iterating through dictionary terms
        terms = list(vclient.dictionary("on-behalf-of-user", company_id="company123").iter_all())

        # Then: Returns list of DictionaryTerm objects
        assert route.called
        assert isinstance(terms, list)

        assert len(terms) == 1
        assert isinstance(terms[0], DictionaryTerm)
        assert terms[0].term == "Test Term"


class TestDictionaryServiceGet:
    """Tests for DictionaryService.get method."""

    @respx.mock
    def test_get(self, vclient, base_url, dictionary_term_response_data):
        """Verify getting a dictionary term."""
        # Given: A mocked dictionary endpoint
        company_id = "company123"
        term_id = "term123"
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERM.format(company_id=company_id, term_id=term_id)}",
        ).respond(200, json=dictionary_term_response_data)

        # When: Getting a dictionary term
        result = vclient.dictionary("on-behalf-of-user", company_id="company123").get(term_id)

        # Then: Returns DictionaryTerm object
        assert route.called
        assert isinstance(result, DictionaryTerm)
        assert result.term == "Test Term"

    @respx.mock
    def test_get_term_without_powers(self, vclient, base_url, dictionary_term_response_data):
        """Verify a term with no powers key parses to an empty powers list."""
        # Given: A mocked dictionary endpoint returning a company-created term
        company_id = "company123"
        term_id = "term123"
        respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERM.format(company_id=company_id, term_id=term_id)}",
        ).respond(200, json=dictionary_term_response_data)

        # When: Getting the dictionary term
        result = vclient.dictionary("on-behalf-of-user", company_id=company_id).get(term_id)

        # Then: powers defaults to an empty list
        assert result.powers == []

    @respx.mock
    def test_get_trait_sourced_term_with_powers(
        self, vclient, base_url, dictionary_term_response_data
    ):
        """Verify a trait-sourced term parses its embedded powers."""
        # Given: A mocked dictionary endpoint returning a trait-sourced term with powers
        company_id = "company123"
        term_id = "term123"
        dictionary_term_response_data |= {
            "source_type": "trait",
            "source_id": "trait123",
            "powers": [
                {
                    "id": "power1",
                    "level": 1,
                    "name": "A Taste for Blood",
                    "description": "Discern a vampire's generation.",
                    "system": "Roll Perception + Occult.",
                    "link": None,
                },
                {
                    "id": "power2",
                    "level": 1,
                    "name": "Rebel's Spark",
                    "description": "Provoke defiance.",
                    "system": None,
                    "link": None,
                },
            ],
        }
        respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERM.format(company_id=company_id, term_id=term_id)}",
        ).respond(200, json=dictionary_term_response_data)

        # When: Getting the dictionary term
        result = vclient.dictionary("on-behalf-of-user", company_id=company_id).get(term_id)

        # Then: Powers are parsed, including several sharing a level
        assert result.source_type == "trait"
        assert len(result.powers) == 2
        assert result.powers[0].name == "A Taste for Blood"
        assert result.powers[0].system == "Roll Perception + Occult."
        assert [p.level for p in result.powers] == [1, 1]

    @respx.mock
    def test_get_not_found(self, vclient, base_url):
        """Verify getting a non-existent dictionary term raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        term_id = "nonexistent"
        route = respx.get(
            f"{base_url}{Endpoints.DICTIONARY_TERM.format(company_id=company_id, term_id=term_id)}",
        ).respond(404, json={"detail": "Dictionary term not found"})

        # When/Then: Getting the dictionary term raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.dictionary("on-behalf-of-user", company_id="company123").get(term_id)

        assert route.called


class TestDictionaryServiceCreate:
    """Tests for DictionaryService.create method."""

    @respx.mock
    def test_create(self, vclient, base_url, dictionary_term_response_data):
        """Verify creating a dictionary term."""
        # Given: A mocked dictionary endpoint
        company_id = "company123"
        route = respx.post(
            f"{base_url}{Endpoints.DICTIONARY_TERMS.format(company_id=company_id)}",
        ).respond(200, json=dictionary_term_response_data)

        # When: Creating a dictionary term
        result = vclient.dictionary("on-behalf-of-user", company_id="company123").create(
            term="Test Term",
            definition="A test definition",
            link="https://example.com",
            synonyms=["Test Synonym", "Test Synonym 2"],
        )

        # Then: Returns DictionaryTerm object
        assert route.called
        assert isinstance(result, DictionaryTerm)
        assert result.term == "Test Term"

        # Verify request body
        request = route.calls.last.request
        body = json.loads(request.content)
        assert body == {
            "term": "Test Term",
            "definition": "A test definition",
            "link": "https://example.com",
            "synonyms": ["Test Synonym", "Test Synonym 2"],
        }


class TestDictionaryServiceUpdate:
    """Tests for DictionaryService.update method."""

    @respx.mock
    def test_update(self, vclient, base_url, dictionary_term_response_data):
        """Verify updating a dictionary term."""
        # Given: A mocked dictionary endpoint
        company_id = "company123"
        term_id = "term123"
        route = respx.patch(
            f"{base_url}{Endpoints.DICTIONARY_TERM.format(company_id=company_id, term_id=term_id)}",
        ).respond(200, json=dictionary_term_response_data)

        # When: Updating a dictionary term
        result = vclient.dictionary("on-behalf-of-user", company_id="company123").update(
            term_id,  # positional argument
            term="Updated Term",
            definition="An updated definition",
            link="https://example.com",
            synonyms=["Updated Synonym", "Updated Synonym 2"],
        )

        # Then: Returns DictionaryTerm object
        assert route.called
        assert isinstance(result, DictionaryTerm)
        assert result.term == "Test Term"
        assert result.definition == "A test definition"
        assert result.link == "https://example.com"
        assert result.synonyms == ["Test Synonym", "Test Synonym 2"]

        # Verify request body
        request = route.calls.last.request
        body = json.loads(request.content)
        assert body == {
            "term": "Updated Term",
            "definition": "An updated definition",
            "link": "https://example.com",
            "synonyms": ["Updated Synonym", "Updated Synonym 2"],
        }


class TestDictionaryServiceDelete:
    """Tests for DictionaryService.delete method."""

    @respx.mock
    def test_delete(self, vclient, base_url, dictionary_term_response_data):
        """Verify deleting a dictionary term."""
        # Given: A mocked dictionary endpoint
        company_id = "company123"
        term_id = "term123"
        route = respx.delete(
            f"{base_url}{Endpoints.DICTIONARY_TERM.format(company_id=company_id, term_id=term_id)}",
        ).respond(200, json=dictionary_term_response_data)

        # When: Deleting a dictionary term
        result = vclient.dictionary("on-behalf-of-user", company_id="company123").delete(term_id)

        # Then: Request was made and returns None
        assert route.called
        assert result is None
