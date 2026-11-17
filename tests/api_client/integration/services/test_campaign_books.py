"""Tests for vweb.api_client.services.campaign_books."""

import pytest
import respx

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import NotFoundError, RequestValidationError
from vweb.api_client.models import Asset, CampaignBook, CampaignBookDetail, Note, PaginatedResponse


@pytest.fixture
def book_response_data() -> dict:
    """Return sample book response data."""
    return {
        "id": "507f1f77bcf86cd799439011",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "name": "Test Book",
        "description": "A test book description",
        "asset_ids": ["asset1", "asset2"],
        "character_ids": [],
        "number": 1,
        "campaign_id": "campaign123",
    }


@pytest.fixture
def paginated_books_response(book_response_data) -> dict:
    """Return sample paginated books response."""
    return {
        "items": [book_response_data],
        "limit": 10,
        "offset": 0,
        "total": 1,
    }


@pytest.fixture
def asset_response_data(asset_response_data_factory) -> dict:
    """Return sample asset response data for a book."""
    return asset_response_data_factory(
        original_filename="book.png",
        public_url="https://example.com/book.png",
        book_id="book123",
    )


class TestBooksServiceGetPage:
    """Tests for BooksService.get_page method."""

    @respx.mock
    def test_get_page_books(self, vclient, base_url, paginated_books_response):
        """Verify get_page returns paginated CampaignBook objects."""
        # Given: A mocked books list endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOKS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_books_response)

        # When: Getting a page of books
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).get_page()

        # Then: Returns PaginatedResponse with CampaignBook objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], CampaignBook)
        assert result.items[0].name == "Test Book"
        assert result.total == 1

    @respx.mock
    def test_get_page_with_pagination(self, vclient, base_url, book_response_data):
        """Verify get_page accepts pagination parameters."""
        # Given: A mocked endpoint expecting custom pagination
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOKS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}",
            params={"limit": "25", "offset": "50"},
        ).respond(
            200,
            json={
                "items": [book_response_data],
                "limit": 25,
                "offset": 50,
                "total": 100,
            },
        )

        # When: Getting a page with custom pagination
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).get_page(
            limit=25, offset=50
        )

        # Then: Request was made with correct params
        assert route.called
        assert result.limit == 25
        assert result.offset == 50


class TestBooksServiceListAll:
    """Tests for BooksService.list_all method."""

    @respx.mock
    def test_list_all_books(self, vclient, base_url, book_response_data):
        """Verify list_all returns all books across pages."""
        # Given: Mocked endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOKS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [book_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Calling list_all
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).list_all()

        # Then: Returns list of CampaignBook objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], CampaignBook)


class TestBooksServiceIterAll:
    """Tests for BooksService.iter_all method."""

    @respx.mock
    def test_iter_all_books(self, vclient, base_url, book_response_data):
        """Verify iter_all yields CampaignBook objects across pages."""
        # Given: Mocked endpoints for multiple pages
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book2 = {
            **book_response_data,
            "id": "507f1f77bcf86cd799439012",
            "name": "Book 2",
            "number": 2,
        }
        respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOKS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}",
            params={"limit": "1", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [book_response_data],
                "limit": 1,
                "offset": 0,
                "total": 2,
            },
        )
        respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOKS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}",
            params={"limit": "1", "offset": "1"},
        ).respond(
            200,
            json={
                "items": [book2],
                "limit": 1,
                "offset": 1,
                "total": 2,
            },
        )

        # When: Iterating through all books
        books = list(
            vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).iter_all(limit=1)
        )

        # Then: All books are yielded as CampaignBook objects
        assert len(books) == 2
        assert all(isinstance(b, CampaignBook) for b in books)
        assert books[0].name == "Test Book"
        assert books[1].name == "Book 2"


class TestBooksServiceGet:
    """Tests for BooksService.get method."""

    @respx.mock
    def test_get_book(self, vclient, base_url, book_response_data):
        """Verify getting a book returns CampaignBook object."""
        # Given: A mocked book endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "507f1f77bcf86cd799439011"
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(200, json=book_response_data)

        # When: Getting the book
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).get(book_id)

        # Then: Returns CampaignBook object with correct data
        assert route.called
        assert isinstance(result, CampaignBook)
        assert result.id == book_id
        assert result.name == "Test Book"
        assert result.number == 1

    @respx.mock
    def test_get_book_not_found(self, vclient, base_url):
        """Verify getting non-existent book raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "nonexistent"
        respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(404, json={"detail": "Book not found"})

        # When/Then: Getting the book raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).get(book_id)

    @respx.mock
    def test_get_book_without_include_returns_detail_with_none_embeds(
        self, vclient, base_url, book_response_data
    ):
        """Verify get() without include returns CampaignBookDetail with all embeds None."""
        # Given: A mocked book endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = book_response_data["id"]
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(200, json=book_response_data)

        # When: Getting the book without include
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).get(book_id)

        # Then: Returns CampaignBookDetail with None embedded fields
        assert route.called
        assert isinstance(result, CampaignBookDetail)
        assert isinstance(result, CampaignBook)
        assert result.chapters is None
        assert result.notes is None
        assert result.assets is None

    @respx.mock
    def test_get_book_with_include_sends_repeated_query_params(
        self, vclient, base_url, book_response_data
    ):
        """Verify get(include=[...]) sends repeated include query params and parses embeds."""
        # Given: A mocked book endpoint with embedded resources in response
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = book_response_data["id"]
        payload = {**book_response_data, "chapters": [], "notes": []}
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(200, json=payload)

        # When: Getting the book with include params
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).get(
            book_id, include=["chapters", "notes"]
        )

        # Then: Request contains repeated include params and embeds are parsed
        assert route.called
        sent_url = str(route.calls.last.request.url)
        assert "include=chapters" in sent_url
        assert "include=notes" in sent_url
        assert isinstance(result, CampaignBookDetail)
        assert result.chapters == []
        assert result.notes == []
        assert result.assets is None


class TestBooksServiceCreate:
    """Tests for BooksService.create method."""

    @respx.mock
    def test_create_book_minimal(self, vclient, base_url, book_response_data):
        """Verify creating book with minimal data."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        route = respx.post(
            f"{base_url}{Endpoints.CAMPAIGN_BOOKS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(201, json=book_response_data)

        # When: Creating a book with minimal data
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).create(
            name="Test Book"
        )

        # Then: Returns created CampaignBook object
        assert route.called
        assert isinstance(result, CampaignBook)
        assert result.name == "Test Book"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Test Book"

    @respx.mock
    def test_create_book_with_all_fields(self, vclient, base_url, book_response_data):
        """Verify creating book with all fields."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        route = respx.post(
            f"{base_url}{Endpoints.CAMPAIGN_BOOKS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(201, json=book_response_data)

        # When: Creating a book with all fields
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).create(
            name="Test Book",
            description="A test book description",
        )

        # Then: Returns created CampaignBook object
        assert route.called
        assert isinstance(result, CampaignBook)

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Test Book"
        assert body["description"] == "A test book description"

    def test_create_book_validation_error(self, vclient):
        """Verify validation error on invalid data raises RequestValidationError."""
        # When/Then: Creating with invalid data raises RequestValidationError
        with pytest.raises(RequestValidationError):
            vclient.books("campaign123", "on-behalf-of-user", company_id="company123").create(
                name="AB"
            )


class TestBooksServiceUpdate:
    """Tests for BooksService.update method."""

    @respx.mock
    def test_update_book_name(self, vclient, base_url, book_response_data):
        """Verify updating book name."""
        # Given: A mocked update endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "507f1f77bcf86cd799439011"
        updated_data = {**book_response_data, "name": "Updated Name"}
        route = respx.patch(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(200, json=updated_data)

        # When: Updating the book name
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).update(
            book_id, name="Updated Name"
        )

        # Then: Returns updated CampaignBook object
        assert route.called
        assert isinstance(result, CampaignBook)
        assert result.name == "Updated Name"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body == {"name": "Updated Name"}

    @respx.mock
    def test_update_book_not_found(self, vclient, base_url):
        """Verify updating non-existent book raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "nonexistent"
        respx.patch(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(404, json={"detail": "Book not found"})

        # When/Then: Updating raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).update(
                book_id, name="New Name"
            )


class TestBooksServiceDelete:
    """Tests for BooksService.delete method."""

    @respx.mock
    def test_delete_book(self, vclient, base_url):
        """Verify deleting a book."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "507f1f77bcf86cd799439011"
        route = respx.delete(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(204)

        # When: Deleting the book
        vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).delete(book_id)

        # Then: Request was made
        assert route.called

    @respx.mock
    def test_delete_book_not_found(self, vclient, base_url):
        """Verify deleting non-existent book raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "nonexistent"
        respx.delete(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(404, json={"detail": "Book not found"})

        # When/Then: Deleting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).delete(book_id)


class TestBooksServiceRenumber:
    """Tests for BooksService.renumber method."""

    @respx.mock
    def test_renumber_book(self, vclient, base_url, book_response_data):
        """Verify renumbering a book."""
        # Given: A mocked renumber endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "507f1f77bcf86cd799439011"
        updated_data = {**book_response_data, "number": 3}
        route = respx.put(
            f"{base_url}{Endpoints.CAMPAIGN_BOOK_NUMBER.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(200, json=updated_data)

        # When: Renumbering the book
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).renumber(
            book_id, number=3
        )

        # Then: Returns updated CampaignBook object
        assert route.called
        assert isinstance(result, CampaignBook)
        assert result.number == 3

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body == {"number": 3}

    def test_renumber_book_validation_error(self, vclient):
        """Verify validation error on invalid number raises RequestValidationError."""
        # When/Then: Renumbering with invalid number raises RequestValidationError
        with pytest.raises(RequestValidationError):
            vclient.books("campaign123", "on-behalf-of-user", company_id="company123").renumber(
                "book_id", number=0
            )


class TestBooksServiceNotes:
    """Tests for BooksService note methods."""

    @respx.mock
    def test_get_notes_page(self, vclient, base_url, note_response_data):
        """Verify getting a page of notes."""
        # Given: A mocked notes endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_NOTES.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [note_response_data],
                "limit": 10,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Getting a page of notes
        result = vclient.books(
            campaign_id, "on-behalf-of-user", company_id=company_id
        ).get_notes_page(book_id)

        # Then: Returns paginated Note objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Note)

    @respx.mock
    def test_list_all_notes(self, vclient, base_url, note_response_data):
        """Verify list_all_notes returns all notes."""
        # Given: A mocked notes endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        respx.get(
            f"{base_url}{Endpoints.BOOK_NOTES.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [note_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Calling list_all_notes
        result = vclient.books(
            campaign_id, "on-behalf-of-user", company_id=company_id
        ).list_all_notes(book_id)

        # Then: Returns list of Note objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Note)

    @respx.mock
    def test_get_note(self, vclient, base_url, note_response_data):
        """Verify getting a specific note."""
        # Given: A mocked note endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        note_id = "note123"
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_NOTE.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, note_id=note_id)}"
        ).respond(200, json=note_response_data)

        # When: Getting the note
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).get_note(
            book_id, note_id
        )

        # Then: Returns Note object
        assert route.called
        assert isinstance(result, Note)
        assert result.id == "note123"
        assert result.title == "Test Note"

    @respx.mock
    def test_create_note(self, vclient, base_url, note_response_data):
        """Verify creating a note."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.post(
            f"{base_url}{Endpoints.BOOK_NOTES.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(201, json=note_response_data)

        # When: Creating a note
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).create_note(
            book_id, title="Test Note", content="This is test content"
        )

        # Then: Returns Note object
        assert route.called
        assert isinstance(result, Note)
        assert result.title == "Test Note"

    @respx.mock
    def test_update_note(self, vclient, base_url, note_response_data):
        """Verify updating a note."""
        # Given: A mocked update endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        note_id = "note123"
        updated_data = {**note_response_data, "title": "Updated Title"}
        route = respx.patch(
            f"{base_url}{Endpoints.BOOK_NOTE.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, note_id=note_id)}"
        ).respond(200, json=updated_data)

        # When: Updating the note
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).update_note(
            book_id, note_id, title="Updated Title"
        )

        # Then: Returns updated Note object
        assert route.called
        assert isinstance(result, Note)
        assert result.title == "Updated Title"

    @respx.mock
    def test_delete_note(self, vclient, base_url):
        """Verify deleting a note."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        note_id = "note123"
        route = respx.delete(
            f"{base_url}{Endpoints.BOOK_NOTE.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, note_id=note_id)}"
        ).respond(204)

        # When: Deleting the note
        vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).delete_note(
            book_id, note_id
        )

        # Then: Request was made
        assert route.called


class TestBooksServiceAssets:
    """Tests for BooksService asset methods."""

    @respx.mock
    def test_get_assets_page(self, vclient, base_url, asset_response_data):
        """Verify getting a page of book assets."""
        # Given: A mocked assets endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_ASSETS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [asset_response_data],
                "limit": 10,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Getting a page of assets
        result = vclient.books(
            campaign_id, "on-behalf-of-user", company_id=company_id
        ).get_assets_page(book_id)

        # Then: Returns paginated Asset objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Asset)

    @respx.mock
    def test_list_all_assets(self, vclient, base_url, asset_response_data):
        """Verify list_all_assets returns all assets."""
        # Given: A mocked assets endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        respx.get(
            f"{base_url}{Endpoints.BOOK_ASSETS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [asset_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Calling list_all_assets
        result = vclient.books(
            campaign_id, "on-behalf-of-user", company_id=company_id
        ).list_all_assets(book_id)

        # Then: Returns list of Asset objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Asset)

    @respx.mock
    def test_get_asset(self, vclient, base_url, asset_response_data):
        """Verify getting a specific asset."""
        # Given: A mocked asset endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        asset_id = "asset123"
        route = respx.get(
            f"{base_url}{Endpoints.BOOK_ASSET.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, asset_id=asset_id)}"
        ).respond(200, json=asset_response_data)

        # When: Getting the asset
        result = vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).get_asset(
            book_id, asset_id
        )

        # Then: Returns Asset object
        assert route.called
        assert isinstance(result, Asset)
        assert result.id == "asset123"

    @respx.mock
    def test_delete_asset(self, vclient, base_url):
        """Verify deleting an asset."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        asset_id = "asset123"
        route = respx.delete(
            f"{base_url}{Endpoints.BOOK_ASSET.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id, asset_id=asset_id)}"
        ).respond(204)

        # When: Deleting the asset
        vclient.books(campaign_id, "on-behalf-of-user", company_id=company_id).delete_asset(
            book_id, asset_id
        )

        # Then: Request was made
        assert route.called

    @respx.mock
    def test_upload_asset(self, vclient, base_url, asset_response_data):
        """Verify uploading an asset."""
        # Given: A mocked upload endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        book_id = "book123"
        route = respx.post(
            f"{base_url}{Endpoints.BOOK_ASSET_UPLOAD.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, book_id=book_id)}"
        ).respond(201, json=asset_response_data)

        # When: Uploading an asset
        result = vclient.books(
            campaign_id, "on-behalf-of-user", company_id=company_id
        ).upload_asset(
            book_id,
            filename="test.png",
            content=b"test content",
            content_type="image/png",
        )

        # Then: Returns Asset object
        assert route.called
        assert isinstance(result, Asset)
        assert result.id == "asset123"
