"""Tests for vweb.api_client.services.campaign_books."""

import pytest

from tests.api_client.payloads import page, sent_json, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import CampaignBook
from vweb.api_client.testing import CampaignBookFactory

COMPANY_ID = "company123"
CAMPAIGN_ID = "campaign123"
BOOK_ID = "book123"
BOOKS = Endpoints.CAMPAIGN_BOOKS.format(company_id=COMPANY_ID, campaign_id=CAMPAIGN_ID)
BOOK = Endpoints.CAMPAIGN_BOOK.format(
    company_id=COMPANY_ID, campaign_id=CAMPAIGN_ID, book_id=BOOK_ID
)


@pytest.fixture
def service(vclient):
    """Return the books service for the test campaign."""
    return vclient.books(CAMPAIGN_ID, "on-behalf-of-user", company_id=COMPANY_ID)


@pytest.fixture
def book() -> CampaignBook:
    """Return a book to serve from the mocked API."""
    return CampaignBookFactory.build(id=BOOK_ID)


@pytest.mark.parametrize(
    ("fetch", "params"),
    [
        pytest.param(
            lambda svc: svc.get_page(limit=25, offset=50).items,
            {"limit": "25", "offset": "50"},
            id="get_page",
        ),
        pytest.param(lambda svc: svc.list_all(), {"limit": "100", "offset": "0"}, id="list_all"),
        pytest.param(
            lambda svc: list(svc.iter_all()), {"limit": "100", "offset": "0"}, id="iter_all"
        ),
    ],
)
def test_list_books(service, mock_api, book, fetch, params):
    """Verify each listing method pages the campaign's books and parses them."""
    route = mock_api.get(BOOKS, params=params).respond(200, json=page(book))

    result = fetch(service)

    assert route.called
    assert [b.id for b in result] == [BOOK_ID]


@pytest.mark.parametrize(
    ("include", "embeds", "expected_query"),
    [
        pytest.param(None, {}, b"", id="no-include"),
        pytest.param(
            ["chapters", "notes"],
            {"chapters": [], "notes": []},
            b"include=chapters&include=notes",
            id="include",
        ),
    ],
)
def test_get_book(service, mock_api, book, include, embeds, expected_query):
    """Verify get sends each include as a repeated query param and parses only those embeds."""
    # Given: A book endpoint returning the requested embeds
    route = mock_api.get(BOOK).respond(200, json={**wire(book), **embeds})

    # When: Getting the book
    result = service.get(BOOK_ID, include=include)

    # Then: The include params are sent and unrequested embeds stay None
    assert route.calls.last.request.url.query == expected_query
    assert result.id == BOOK_ID
    for field in ("chapters", "notes", "assets"):
        assert getattr(result, field) == embeds.get(field)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"name": "Test Book"}, id="minimal"),
        pytest.param({"name": "Test Book", "description": "A description"}, id="all-fields"),
    ],
)
def test_create_book(service, mock_api, book, kwargs):
    """Verify create POSTs only the given fields and parses the created book."""
    route = mock_api.post(BOOKS).respond(201, json=wire(book))

    result = service.create(**kwargs)

    assert sent_json(route) == kwargs
    assert result.id == BOOK_ID


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"name": "Updated Name"}, id="name"),
        pytest.param({"description": None}, id="clear-description"),
    ],
)
def test_update_book(service, mock_api, book, kwargs):
    """Verify update PATCHes only the given fields, sending null to clear the description."""
    route = mock_api.patch(BOOK).respond(200, json=wire(book))

    result = service.update(BOOK_ID, **kwargs)

    assert sent_json(route) == kwargs
    assert result.id == BOOK_ID


def test_delete_book(service, mock_api):
    """Verify delete sends a DELETE to the book."""
    route = mock_api.delete(BOOK).respond(204)

    assert service.delete(BOOK_ID) is None
    assert route.called


def test_renumber_book(service, mock_api, book):
    """Verify renumber PUTs the new number and parses the renumbered book."""
    route = mock_api.put(
        Endpoints.CAMPAIGN_BOOK_NUMBER.format(
            company_id=COMPANY_ID, campaign_id=CAMPAIGN_ID, book_id=BOOK_ID
        )
    ).respond(200, json=wire(book.model_copy(update={"number": 3})))

    result = service.renumber(BOOK_ID, number=3)

    assert sent_json(route) == {"number": 3}
    assert result.number == 3
