"""Tests for vweb.api_client.services.campaign_book_chapters."""

import pytest
import respx

from tests.api_client.payloads import page, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import NotFoundError
from vweb.api_client.models import CampaignChapter, PaginatedResponse
from vweb.api_client.testing import CampaignChapterFactory


@pytest.fixture
def chapter_response_data() -> dict:
    """Return chapter response data."""
    return wire(
        CampaignChapterFactory.build(
            id="507f1f77bcf86cd799439011",
            name="Test Chapter",
            number=1,
            character_ids=["char1", "char2"],
        )
    )


@pytest.fixture
def paginated_chapters_response(chapter_response_data) -> dict:
    """Return a one-item paginated chapters response."""
    return page(chapter_response_data)


class TestChaptersServiceGetPage:
    """Tests for ChaptersService.get_page method."""

    @respx.mock
    def test_get_page_chapters(self, vclient, base_url, paginated_chapters_response):
        """Verify get_page returns paginated CampaignChapter objects."""
        # Given: A mocked chapters list endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTERS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_chapters_response)

        # When: Getting a page of chapters
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).get_page()

        # Then: Returns PaginatedResponse with CampaignChapter objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], CampaignChapter)
        assert result.items[0].name == "Test Chapter"
        assert result.total == 1

    @respx.mock
    def test_get_page_with_pagination(self, vclient, base_url, chapter_response_data):
        """Verify get_page accepts pagination parameters."""
        # Given: A mocked endpoint expecting custom pagination
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTERS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "25", "offset": "50"},
        ).respond(
            200,
            json=page(chapter_response_data, limit=25, offset=50, total=100),
        )

        # When: Getting a page with custom pagination
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).get_page(limit=25, offset=50)

        # Then: Request was made with correct params
        assert route.called
        assert result.limit == 25
        assert result.offset == 50


class TestChaptersServiceListAll:
    """Tests for ChaptersService.list_all method."""

    @respx.mock
    def test_list_all_chapters(self, vclient, base_url, chapter_response_data):
        """Verify list_all returns all chapters across pages."""
        # Given: Mocked endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTERS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json=page(chapter_response_data, limit=100),
        )

        # When: Calling list_all
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).list_all()

        # Then: Returns list of CampaignChapter objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], CampaignChapter)


class TestChaptersServiceIterAll:
    """Tests for ChaptersService.iter_all method."""

    @respx.mock
    def test_iter_all_chapters(self, vclient, base_url, chapter_response_data):
        """Verify iter_all yields CampaignChapter objects across pages."""
        # Given: Mocked endpoints for multiple pages
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter2 = {
            **chapter_response_data,
            "id": "507f1f77bcf86cd799439012",
            "name": "Chapter 2",
            "number": 2,
        }
        respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTERS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "1", "offset": "0"},
        ).respond(
            200,
            json=page(chapter_response_data, limit=1, total=2),
        )
        respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTERS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "1", "offset": "1"},
        ).respond(
            200,
            json=page(chapter2, limit=1, offset=1, total=2),
        )

        # When: Iterating through all chapters
        chapters = list(
            vclient.chapters(
                campaign_id, book_id, "on-behalf-of-user", company_id=company_id
            ).iter_all(limit=1)
        )

        # Then: All chapters are yielded as CampaignChapter objects
        assert len(chapters) == 2
        assert all(isinstance(c, CampaignChapter) for c in chapters)
        assert chapters[0].name == "Test Chapter"
        assert chapters[1].name == "Chapter 2"


class TestChaptersServiceGetWithInclude:
    """Tests for ChaptersService.get() with include parameter."""

    @respx.mock
    def test_get_chapter_without_include_returns_detail_with_none_embeds(
        self, vclient, base_url, chapter_response_data
    ):
        """Verify get() without include returns CampaignChapterDetail with all embeds None."""
        from vweb.api_client.models import CampaignChapterDetail

        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = chapter_response_data["id"]
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(200, json=chapter_response_data)

        # When: Getting the chapter without include
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).get(chapter_id)

        # Then: Returns CampaignChapterDetail with embeds all None
        assert route.called
        assert isinstance(result, CampaignChapterDetail)
        assert result.notes is None
        assert result.assets is None

    @respx.mock
    def test_get_chapter_with_include_sends_repeated_query_params(
        self, vclient, base_url, chapter_response_data
    ):
        """Verify get(include=[...]) sends repeated include query params and parses embeds."""
        from vweb.api_client.models import CampaignChapterDetail

        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = chapter_response_data["id"]
        payload = {**chapter_response_data, "notes": [], "assets": []}
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(200, json=payload)

        # When: Getting the chapter with include
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).get(chapter_id, include=["notes", "assets"])

        # Then: Request sent with repeated include params and embeds are parsed
        assert route.called
        sent_url = str(route.calls.last.request.url)
        assert "include=notes" in sent_url
        assert "include=assets" in sent_url
        assert isinstance(result, CampaignChapterDetail)
        assert result.notes == []
        assert result.assets == []


class TestChaptersServiceGet:
    """Tests for ChaptersService.get method."""

    @respx.mock
    def test_get_chapter(self, vclient, base_url, chapter_response_data):
        """Verify getting a chapter returns CampaignChapter object."""
        # Given: A mocked chapter endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = "507f1f77bcf86cd799439011"
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(200, json=chapter_response_data)

        # When: Getting the chapter
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).get(chapter_id)

        # Then: Returns CampaignChapter object with correct data
        assert route.called
        assert isinstance(result, CampaignChapter)
        assert result.id == chapter_id
        assert result.name == "Test Chapter"
        assert result.number == 1

    @respx.mock
    def test_get_chapter_not_found(self, vclient, base_url):
        """Verify getting non-existent chapter raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = "nonexistent"
        respx.get(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(404, json={"detail": "Chapter not found"})

        # When/Then: Getting the chapter raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.chapters(campaign_id, book_id, "on-behalf-of-user", company_id=company_id).get(
                chapter_id
            )


class TestChaptersServiceCreate:
    """Tests for ChaptersService.create method."""

    @respx.mock
    def test_create_chapter_minimal(self, vclient, base_url, chapter_response_data):
        """Verify creating chapter with minimal data."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.post(
            f"{base_url}{Endpoints.BOOK_CHAPTERS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(201, json=chapter_response_data)

        # When: Creating a chapter with minimal data
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).create(name="Test Chapter")

        # Then: Returns created CampaignChapter object
        assert route.called
        assert isinstance(result, CampaignChapter)
        assert result.name == "Test Chapter"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Test Chapter"

    @respx.mock
    def test_create_chapter_with_description(self, vclient, base_url, chapter_response_data):
        """Verify creating chapter with all fields."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.post(
            f"{base_url}{Endpoints.BOOK_CHAPTERS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(201, json=chapter_response_data)

        # When: Creating a chapter with all fields
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).create(
            name="Test Chapter",
            description="A test chapter description",
        )

        # Then: Returns created CampaignChapter object
        assert route.called
        assert isinstance(result, CampaignChapter)

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Test Chapter"
        assert body["description"] == "A test chapter description"

    @respx.mock
    def test_create_chapter_with_character_ids(self, vclient, base_url, chapter_response_data):
        """Verify create sends character_ids in the request body."""
        # Given: a mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.post(
            f"{base_url}{Endpoints.BOOK_CHAPTERS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(201, json=chapter_response_data)

        # When: creating a chapter with character_ids
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).create(name="Test Chapter", character_ids=["char1", "char2"])

        # Then: the body carries character_ids and the response parses them
        assert route.called
        import json

        body = json.loads(route.calls.last.request.content)
        assert body["character_ids"] == ["char1", "char2"]
        assert result.character_ids == ["char1", "char2"]


class TestChaptersServiceUpdate:
    """Tests for ChaptersService.update method."""

    @respx.mock
    def test_update_chapter_name(self, vclient, base_url, chapter_response_data):
        """Verify updating chapter name."""
        # Given: A mocked update endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = "507f1f77bcf86cd799439011"
        updated_data = {**chapter_response_data, "name": "Updated Name"}
        route = respx.patch(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(200, json=updated_data)

        # When: Updating the chapter name
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).update(chapter_id, name="Updated Name")

        # Then: Returns updated CampaignChapter object
        assert route.called
        assert isinstance(result, CampaignChapter)
        assert result.name == "Updated Name"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Updated Name"

    @respx.mock
    def test_update_chapter_clears_description(self, vclient, base_url, chapter_response_data):
        """Verify description=None sends null so the API clears it."""
        # Given: A mocked update endpoint
        route = respx.patch(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id='company123', campaign_id='campaign123', book_id='book1', chapter_id='chap1')}"
        ).respond(200, json={**chapter_response_data, "description": None})

        # When: Clearing the description
        vclient.chapters(
            "campaign123", "book1", "on-behalf-of-user", company_id="company123"
        ).update("chap1", description=None)

        # Then: The description is sent as null
        import json

        assert json.loads(route.calls.last.request.content) == {"description": None}

    @respx.mock
    def test_update_chapter_clears_character_ids(self, vclient, base_url, chapter_response_data):
        """Verify update sends an explicit empty list to clear associations."""
        # Given: a mocked update endpoint returning no characters
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = "507f1f77bcf86cd799439011"
        cleared = {**chapter_response_data, "character_ids": []}
        route = respx.patch(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(200, json=cleared)

        # When: updating with character_ids=[]
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).update(chapter_id, character_ids=[])

        # Then: an empty list is sent and parsed back
        assert route.called
        import json

        body = json.loads(route.calls.last.request.content)
        assert body["character_ids"] == []
        assert result.character_ids == []

    @respx.mock
    def test_update_chapter_not_found(self, vclient, base_url):
        """Verify updating non-existent chapter raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = "nonexistent"
        respx.patch(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(404, json={"detail": "Chapter not found"})

        # When/Then: Updating raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.chapters(
                campaign_id, book_id, "on-behalf-of-user", company_id=company_id
            ).update(chapter_id, name="New Name")


class TestChaptersServiceDelete:
    """Tests for ChaptersService.delete method."""

    @respx.mock
    def test_delete_chapter(self, vclient, base_url):
        """Verify deleting a chapter."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = "507f1f77bcf86cd799439011"
        route = respx.delete(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(204)

        # When: Deleting the chapter
        vclient.chapters(campaign_id, book_id, "on-behalf-of-user", company_id=company_id).delete(
            chapter_id
        )

        # Then: Request was made
        assert route.called

    @respx.mock
    def test_delete_chapter_not_found(self, vclient, base_url):
        """Verify deleting non-existent chapter raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = "nonexistent"
        respx.delete(
            f"{base_url}{Endpoints.BOOK_CHAPTER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(404, json={"detail": "Chapter not found"})

        # When/Then: Deleting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.chapters(
                campaign_id, book_id, "on-behalf-of-user", company_id=company_id
            ).delete(chapter_id)


class TestChaptersServiceRenumber:
    """Tests for ChaptersService.renumber method."""

    @respx.mock
    def test_renumber_chapter(self, vclient, base_url, chapter_response_data):
        """Verify renumbering a chapter."""
        # Given: A mocked renumber endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        chapter_id = "507f1f77bcf86cd799439011"
        updated_data = {**chapter_response_data, "number": 3}
        route = respx.put(
            f"{base_url}{Endpoints.BOOK_CHAPTER_NUMBER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, chapter_id=chapter_id)}"
        ).respond(200, json=updated_data)

        # When: Renumbering the chapter
        result = vclient.chapters(
            campaign_id, book_id, "on-behalf-of-user", company_id=company_id
        ).renumber(chapter_id, number=3)

        # Then: Returns updated CampaignChapter object
        assert route.called
        assert isinstance(result, CampaignChapter)
        assert result.number == 3

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body == {"number": 3}
