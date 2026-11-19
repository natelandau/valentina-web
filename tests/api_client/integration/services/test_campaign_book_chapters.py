"""Tests for vweb.api_client.services.campaign_book_chapters."""

import pytest

from tests.api_client.payloads import page, sent_json, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import CampaignChapter
from vweb.api_client.testing import CampaignChapterFactory

COMPANY_ID = "company123"
CAMPAIGN_ID = "campaign123"
BOOK_ID = "book123"
CHAPTER_ID = "chapter123"
_IDS = {"company_id": COMPANY_ID, "campaign_id": CAMPAIGN_ID, "book_id": BOOK_ID}
CHAPTERS = Endpoints.BOOK_CHAPTERS.format(**_IDS)
CHAPTER = Endpoints.BOOK_CHAPTER.format(**_IDS, chapter_id=CHAPTER_ID)


@pytest.fixture
def service(vclient):
    """Return the chapters service for the test book."""
    return vclient.chapters(CAMPAIGN_ID, BOOK_ID, "on-behalf-of-user", company_id=COMPANY_ID)


@pytest.fixture
def chapter() -> CampaignChapter:
    """Return a chapter to serve from the mocked API."""
    return CampaignChapterFactory.build(id=CHAPTER_ID, character_ids=["char1", "char2"])


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
def test_list_chapters(service, mock_api, chapter, fetch, params):
    """Verify each listing method pages the book's chapters and parses them."""
    route = mock_api.get(CHAPTERS, params=params).respond(200, json=page(chapter))

    result = fetch(service)

    assert route.called
    assert result == [chapter]


@pytest.mark.parametrize(
    ("include", "embeds", "expected_query"),
    [
        pytest.param(None, {}, b"", id="no-include"),
        pytest.param(
            ["notes", "assets"],
            {"notes": [], "assets": []},
            b"include=notes&include=assets",
            id="include",
        ),
    ],
)
def test_get_chapter(service, mock_api, chapter, include, embeds, expected_query):
    """Verify get sends each include as a repeated query param and parses only those embeds."""
    route = mock_api.get(CHAPTER).respond(200, json={**wire(chapter), **embeds})

    result = service.get(CHAPTER_ID, include=include)

    assert route.calls.last.request.url.query == expected_query
    assert result.character_ids == ["char1", "char2"]
    for field in ("notes", "assets"):
        assert getattr(result, field) == embeds.get(field)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"name": "Test Chapter"}, id="minimal"),
        pytest.param(
            {
                "name": "Test Chapter",
                "description": "A description",
                "character_ids": ["char1", "char2"],
            },
            id="all-fields",
        ),
    ],
)
def test_create_chapter(service, mock_api, chapter, kwargs):
    """Verify create POSTs only the given fields and parses the created chapter."""
    route = mock_api.post(CHAPTERS).respond(201, json=wire(chapter))

    result = service.create(**kwargs)

    assert sent_json(route) == kwargs
    assert result == chapter


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"name": "Updated Name"}, id="name"),
        pytest.param({"description": None}, id="clear-description"),
        pytest.param({"character_ids": []}, id="clear-characters"),
    ],
)
def test_update_chapter(service, mock_api, chapter, kwargs):
    """Verify update PATCHes only the given fields, including null or empty values that clear."""
    route = mock_api.patch(CHAPTER).respond(200, json=wire(chapter))

    result = service.update(CHAPTER_ID, **kwargs)

    assert sent_json(route) == kwargs
    assert result == chapter


def test_delete_chapter(service, mock_api):
    """Verify delete sends a DELETE to the chapter."""
    route = mock_api.delete(CHAPTER).respond(204)

    assert service.delete(CHAPTER_ID) is None
    assert route.called


def test_renumber_chapter(service, mock_api, chapter):
    """Verify renumber PUTs the new number and parses the renumbered chapter."""
    route = mock_api.put(
        Endpoints.BOOK_CHAPTER_NUMBER.format(**_IDS, chapter_id=CHAPTER_ID)
    ).respond(200, json=wire(chapter.model_copy(update={"number": 3})))

    result = service.renumber(CHAPTER_ID, number=3)

    assert sent_json(route) == {"number": 3}
    assert result.number == 3
