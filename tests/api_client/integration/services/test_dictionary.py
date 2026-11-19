"""Integration tests for DictionaryService."""

import pytest

from tests.api_client.payloads import page, sent_json, sent_params, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import DictionaryTerm
from vweb.api_client.testing import DictionaryTermFactory

COMPANY_ID = "company123"
TERM_ID = "term123"
TERMS = Endpoints.DICTIONARY_TERMS.format(company_id=COMPANY_ID)
TERM = Endpoints.DICTIONARY_TERM.format(company_id=COMPANY_ID, term_id=TERM_ID)


@pytest.fixture
def service(vclient):
    """Return the dictionary service for the test company."""
    return vclient.dictionary("on-behalf-of-user", company_id=COMPANY_ID)


@pytest.fixture
def term() -> DictionaryTerm:
    """Return a dictionary term to serve from the mocked API."""
    return DictionaryTermFactory.build(id=TERM_ID)


@pytest.mark.parametrize(
    ("fetch", "expected_params"),
    [
        pytest.param(
            lambda svc: svc.get_page().items, {"limit": "10", "offset": "0"}, id="get_page-default"
        ),
        pytest.param(
            lambda svc: svc.get_page(limit=1000, offset=50, term="Blood").items,
            {"limit": "1000", "offset": "50", "term": "Blood"},
            id="get_page-reference-limit",
        ),
        pytest.param(
            lambda svc: svc.list_all(term="Blood"),
            {"limit": "1000", "offset": "0", "term": "Blood"},
            id="list_all",
        ),
        pytest.param(
            lambda svc: list(svc.iter_all(term="Blood")),
            {"limit": "1000", "offset": "0", "term": "Blood"},
            id="iter_all",
        ),
    ],
)
def test_list_terms(service, mock_api, term, fetch, expected_params):
    """Verify listing pages up to the 1000-item reference limit and sends the term filter."""
    route = mock_api.get(TERMS).respond(200, json=page(term))

    result = fetch(service)

    assert sent_params(route) == expected_params
    assert result == [term]


@pytest.mark.parametrize(
    ("extra", "expected_powers"),
    [
        pytest.param({}, [], id="no-powers-key"),
        pytest.param(
            {
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
            },
            [("A Taste for Blood", 1), ("Rebel's Spark", 1)],
            id="trait-sourced-powers",
        ),
    ],
)
def test_get_term(service, mock_api, term, extra, expected_powers):
    """Verify get parses a term's powers, defaulting to none when the key is absent."""
    # Given: A term payload with or without embedded powers
    payload = {k: v for k, v in wire(term).items() if k != "powers"} | extra
    route = mock_api.get(TERM).respond(200, json=payload)

    # When: Getting the term
    result = service.get(TERM_ID)

    # Then: Powers parse, including several sharing a level
    assert route.called
    assert result.id == TERM_ID
    assert [(p.name, p.level) for p in result.powers] == expected_powers


def test_create_term(service, mock_api, term):
    """Verify create POSTs the term's fields and parses the created term."""
    route = mock_api.post(TERMS).respond(201, json=wire(term))
    fields = {
        "term": "Test Term",
        "definition": "A test definition",
        "link": "https://example.com",
        "synonyms": ["Test Synonym", "Test Synonym 2"],
    }

    result = service.create(**fields)

    assert sent_json(route) == fields
    assert result == term


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(
            {
                "term": "Updated Term",
                "definition": "An updated definition",
                "link": "https://example.com",
                "synonyms": ["Updated Synonym"],
            },
            id="all-fields",
        ),
        pytest.param({"definition": None, "link": None}, id="clear-definition-and-link"),
    ],
)
def test_update_term(service, mock_api, term, kwargs):
    """Verify update PATCHes only the given fields, sending null to clear definition or link."""
    route = mock_api.patch(TERM).respond(200, json=wire(term))

    result = service.update(TERM_ID, **kwargs)

    assert sent_json(route) == kwargs
    assert result == term


def test_delete_term(service, mock_api):
    """Verify delete sends a DELETE to the term."""
    route = mock_api.delete(TERM).respond(204)

    assert service.delete(TERM_ID) is None
    assert route.called
