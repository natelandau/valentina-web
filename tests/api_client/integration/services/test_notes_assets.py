"""Tests for the note and asset methods every parent-resource service shares."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from tests.api_client.payloads import page, wire
from vweb.api_client import VClient
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import NotFoundError
from vweb.api_client.models import Asset, Note, PaginatedResponse
from vweb.api_client.testing import AssetFactory, NoteFactory

ON_BEHALF_OF = "on-behalf-of-user"
NOTE_ID = "note123"
ASSET_ID = "asset123"
# Distinct ids so a path that fills the wrong placeholder fails to match
IDS = {
    "company_id": "company123",
    "user_id": "user123",
    "campaign_id": "campaign123",
    "book_id": "book123",
    "chapter_id": "chapter123",
    "character_id": "char123",
}


@dataclass(frozen=True)
class ParentCase:
    """One service whose resource owns notes and assets, with that resource's endpoints."""

    name: str
    service: Callable[[VClient], Any]
    parent_id_param: str
    notes: str
    note: str
    assets: str
    asset: str
    upload: str

    @property
    def parent_id(self) -> str:
        """Return the parent resource's id."""
        return IDS[self.parent_id_param]

    def url(self, base_url: str, endpoint: str) -> str:
        """Return the full URL of an endpoint for this parent."""
        return f"{base_url}{endpoint.format(**IDS, note_id=NOTE_ID, asset_id=ASSET_ID)}"


CASES = [
    ParentCase(
        name="campaigns",
        service=lambda c: c.campaigns(ON_BEHALF_OF, company_id=IDS["company_id"]),
        parent_id_param="campaign_id",
        notes=Endpoints.CAMPAIGN_NOTES,
        note=Endpoints.CAMPAIGN_NOTE,
        assets=Endpoints.CAMPAIGN_ASSETS,
        asset=Endpoints.CAMPAIGN_ASSET,
        upload=Endpoints.CAMPAIGN_ASSET_UPLOAD,
    ),
    ParentCase(
        name="books",
        service=lambda c: c.books(IDS["campaign_id"], ON_BEHALF_OF, company_id=IDS["company_id"]),
        parent_id_param="book_id",
        notes=Endpoints.BOOK_NOTES,
        note=Endpoints.BOOK_NOTE,
        assets=Endpoints.BOOK_ASSETS,
        asset=Endpoints.BOOK_ASSET,
        upload=Endpoints.BOOK_ASSET_UPLOAD,
    ),
    ParentCase(
        name="chapters",
        service=lambda c: c.chapters(
            IDS["campaign_id"], IDS["book_id"], ON_BEHALF_OF, company_id=IDS["company_id"]
        ),
        parent_id_param="chapter_id",
        notes=Endpoints.BOOK_CHAPTER_NOTES,
        note=Endpoints.BOOK_CHAPTER_NOTE,
        assets=Endpoints.BOOK_CHAPTER_ASSETS,
        asset=Endpoints.BOOK_CHAPTER_ASSET,
        upload=Endpoints.BOOK_CHAPTER_ASSET_UPLOAD,
    ),
    ParentCase(
        name="characters",
        service=lambda c: c.characters(ON_BEHALF_OF, company_id=IDS["company_id"]),
        parent_id_param="character_id",
        notes=Endpoints.CHARACTER_NOTES,
        note=Endpoints.CHARACTER_NOTE,
        assets=Endpoints.CHARACTER_ASSETS,
        asset=Endpoints.CHARACTER_ASSET,
        upload=Endpoints.CHARACTER_ASSET_UPLOAD,
    ),
    ParentCase(
        name="users",
        service=lambda c: c.users(ON_BEHALF_OF, company_id=IDS["company_id"]),
        parent_id_param="user_id",
        notes=Endpoints.USER_NOTES,
        note=Endpoints.USER_NOTE,
        assets=Endpoints.USER_ASSETS,
        asset=Endpoints.USER_ASSET,
        upload=Endpoints.USER_ASSET_UPLOAD,
    ),
]


@pytest.fixture(params=CASES, ids=lambda case: case.name)
def case(request) -> ParentCase:
    """Return each parent-resource case in turn."""
    return request.param


@pytest.fixture
def service(case, vclient) -> Any:
    """Return the service under test for the current case."""
    return case.service(vclient)


@pytest.fixture
def note() -> Note:
    """Return a note to serve from the mocked API."""
    return NoteFactory.build(id=NOTE_ID)


@pytest.fixture
def asset() -> Asset:
    """Return an asset to serve from the mocked API."""
    return AssetFactory.build(id=ASSET_ID)


class TestNotes:
    """Tests for the shared note methods."""

    def test_get_notes_page(self, case, service, mock_api, base_url, note):
        """Verify get_notes_page requests the default page and parses Note items."""
        # Given: A mocked notes endpoint expecting the default pagination
        route = mock_api.get(
            case.url(base_url, case.notes), params={"limit": "10", "offset": "0"}
        ).respond(200, json=page(note))

        # When: Getting a page of notes
        result = service.get_notes_page(case.parent_id)

        # Then: The page is parsed into Note objects
        assert route.called
        assert route.calls.last.request.headers["On-Behalf-Of"] == ON_BEHALF_OF
        assert isinstance(result, PaginatedResponse)
        assert result.items == [note]
        assert result.total == 1

    def test_list_all_notes(self, case, service, mock_api, base_url, note):
        """Verify list_all_notes pages with limit 100 and returns every Note."""
        # Given: A mocked notes endpoint expecting the iteration page size
        route = mock_api.get(
            case.url(base_url, case.notes), params={"limit": "100", "offset": "0"}
        ).respond(200, json=page(note, limit=100))

        # When: Listing all notes
        result = service.list_all_notes(case.parent_id)

        # Then: Every note is returned
        assert route.called
        assert result == [note]

    def test_get_note(self, case, service, mock_api, base_url, note):
        """Verify get_note fetches one note by id."""
        # Given: A mocked note endpoint
        route = mock_api.get(case.url(base_url, case.note)).respond(200, json=wire(note))

        # When: Getting the note
        result = service.get_note(case.parent_id, NOTE_ID)

        # Then: The note is parsed
        assert route.called
        assert result == note

    def test_get_note_not_found(self, case, service, mock_api, base_url):
        """Verify a 404 on get_note raises NotFoundError."""
        # Given: The note endpoint returns 404
        mock_api.get(case.url(base_url, case.note)).respond(404, json={"detail": "Not found"})

        # When/Then: The error surfaces as NotFoundError
        with pytest.raises(NotFoundError):
            service.get_note(case.parent_id, NOTE_ID)

    def test_create_note(self, case, service, mock_api, base_url, note):
        """Verify create_note POSTs the title and content and parses the created Note."""
        # Given: A mocked create endpoint
        route = mock_api.post(case.url(base_url, case.notes)).respond(201, json=wire(note))

        # When: Creating a note
        result = service.create_note(case.parent_id, title="Test Note", content="Body")

        # Then: The body carries the fields and the created note is returned
        assert route.called
        assert json.loads(route.calls.last.request.content) == {
            "title": "Test Note",
            "content": "Body",
        }
        assert result == note

    def test_update_note(self, case, service, mock_api, base_url, note):
        """Verify update_note PATCHes only the given fields and parses the updated Note."""
        # Given: A mocked update endpoint returning the renamed note
        updated = note.model_copy(update={"title": "Updated Title"})
        route = mock_api.patch(case.url(base_url, case.note)).respond(200, json=wire(updated))

        # When: Updating the title only
        result = service.update_note(case.parent_id, NOTE_ID, title="Updated Title")

        # Then: Only the title is sent and the updated note is returned
        assert route.called
        assert json.loads(route.calls.last.request.content) == {"title": "Updated Title"}
        assert result.title == "Updated Title"

    def test_delete_note(self, case, service, mock_api, base_url):
        """Verify delete_note sends a DELETE to the note."""
        # Given: A mocked delete endpoint
        route = mock_api.delete(case.url(base_url, case.note)).respond(204)

        # When: Deleting the note
        result = service.delete_note(case.parent_id, NOTE_ID)

        # Then: The request was made and nothing is returned
        assert route.called
        assert result is None


class TestAssets:
    """Tests for the shared asset methods."""

    def test_get_assets_page(self, case, service, mock_api, base_url, asset):
        """Verify get_assets_page requests the default page and parses Asset items."""
        # Given: A mocked assets endpoint expecting the default pagination
        route = mock_api.get(
            case.url(base_url, case.assets), params={"limit": "10", "offset": "0"}
        ).respond(200, json=page(asset))

        # When: Getting a page of assets
        result = service.get_assets_page(case.parent_id)

        # Then: The page is parsed into Asset objects
        assert route.called
        assert route.calls.last.request.headers["On-Behalf-Of"] == ON_BEHALF_OF
        assert isinstance(result, PaginatedResponse)
        assert result.items == [asset]
        assert result.total == 1

    def test_list_all_assets(self, case, service, mock_api, base_url, asset):
        """Verify list_all_assets pages with limit 100 and returns every Asset."""
        # Given: A mocked assets endpoint expecting the iteration page size
        route = mock_api.get(
            case.url(base_url, case.assets), params={"limit": "100", "offset": "0"}
        ).respond(200, json=page(asset, limit=100))

        # When: Listing all assets
        result = service.list_all_assets(case.parent_id)

        # Then: Every asset is returned
        assert route.called
        assert result == [asset]

    def test_get_asset(self, case, service, mock_api, base_url, asset):
        """Verify get_asset fetches one asset by id."""
        # Given: A mocked asset endpoint
        route = mock_api.get(case.url(base_url, case.asset)).respond(200, json=wire(asset))

        # When: Getting the asset
        result = service.get_asset(case.parent_id, ASSET_ID)

        # Then: The asset is parsed
        assert route.called
        assert result == asset

    def test_delete_asset(self, case, service, mock_api, base_url):
        """Verify delete_asset sends a DELETE to the asset."""
        # Given: A mocked delete endpoint
        route = mock_api.delete(case.url(base_url, case.asset)).respond(204)

        # When: Deleting the asset
        result = service.delete_asset(case.parent_id, ASSET_ID)

        # Then: The request was made and nothing is returned
        assert route.called
        assert result is None

    @pytest.mark.parametrize(
        ("filename", "content_type", "expected_type"),
        [
            pytest.param("test.png", "image/webp", "image/webp", id="explicit"),
            pytest.param("test.png", None, "image/png", id="guessed"),
            pytest.param("test.unknownext", None, "application/octet-stream", id="fallback"),
        ],
    )
    def test_upload_asset(
        self, case, service, mock_api, base_url, asset, filename, content_type, expected_type
    ):
        """Verify upload_asset POSTs multipart data with the given or guessed content type."""
        # Given: A mocked upload endpoint
        route = mock_api.post(case.url(base_url, case.upload)).respond(201, json=wire(asset))

        # When: Uploading a file
        result = service.upload_asset(
            case.parent_id, filename=filename, content=b"file bytes", content_type=content_type
        )

        # Then: The file goes in the multipart "data" field with the expected content type
        request = route.calls.last.request
        assert "multipart/form-data" in request.headers["content-type"]
        assert f'name="data"; filename="{filename}"'.encode() in request.content
        assert f"Content-Type: {expected_type}".encode() in request.content
        assert b"file bytes" in request.content
        assert result == asset
