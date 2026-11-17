"""Tests for the notes CRUD handlers (book, chapter, character)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from tests.helpers import build_global_context, seed_session
from vweb.api_client.testing import CampaignFactory, CharacterFactory, NoteFactory, Routes
from vweb.routes.book.handlers import BookNotesHandler
from vweb.routes.campaign_notes.handlers import CampaignNotesHandler
from vweb.routes.chapter.handlers import ChapterNotesHandler
from vweb.routes.character_view.handlers_notes import CharacterNotesHandler

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

    from vweb.api_client.routes import RouteSpec


@dataclass(frozen=True)
class NotesHandlerCase:
    """Describe one notes handler variant for the shared validation and CRUD tests."""

    handler_class: type
    list_route: RouteSpec
    get_route: RouteSpec
    create_route: RouteSpec
    update_route: RouteSpec
    delete_route: RouteSpec
    parent_id: str
    path_params: dict[str, str]
    handler_kwargs: dict[str, str] = field(default_factory=dict)
    needs_character_in_context: bool = False


NOTES_HANDLER_CASES: dict[str, NotesHandlerCase] = {
    "book": NotesHandlerCase(
        handler_class=BookNotesHandler,
        list_route=Routes.BOOKS_NOTES_LIST,
        get_route=Routes.BOOKS_NOTES_GET,
        create_route=Routes.BOOKS_NOTES_CREATE,
        update_route=Routes.BOOKS_NOTES_UPDATE,
        delete_route=Routes.BOOKS_NOTES_DELETE,
        parent_id="book-123",
        path_params={"campaign_id": "camp-456", "book_id": "book-123"},
        handler_kwargs={"campaign_id": "camp-456"},
    ),
    "chapter": NotesHandlerCase(
        handler_class=ChapterNotesHandler,
        list_route=Routes.CHAPTERS_NOTES_LIST,
        get_route=Routes.CHAPTERS_NOTES_GET,
        create_route=Routes.CHAPTERS_NOTES_CREATE,
        update_route=Routes.CHAPTERS_NOTES_UPDATE,
        delete_route=Routes.CHAPTERS_NOTES_DELETE,
        parent_id="chapter-123",
        path_params={"campaign_id": "camp-456", "book_id": "book-789", "chapter_id": "chapter-123"},
        handler_kwargs={"campaign_id": "camp-456", "book_id": "book-789"},
    ),
    "character": NotesHandlerCase(
        handler_class=CharacterNotesHandler,
        list_route=Routes.CHARACTERS_NOTES_LIST,
        get_route=Routes.CHARACTERS_NOTES_GET,
        create_route=Routes.CHARACTERS_NOTES_CREATE,
        update_route=Routes.CHARACTERS_NOTES_UPDATE,
        delete_route=Routes.CHARACTERS_NOTES_DELETE,
        parent_id="char-123",
        path_params={"character_id": "char-123"},
        needs_character_in_context=True,
    ),
}


@pytest.fixture(params=sorted(NOTES_HANDLER_CASES))
def handler_case(request: pytest.FixtureRequest) -> NotesHandlerCase:
    """Parametrize over the three notes handler variants."""
    return NOTES_HANDLER_CASES[request.param]


@pytest.fixture
def handler_in_context(app, handler_case, mock_global_context, fake_vclient) -> Iterator[object]:
    """Construct the handler inside a seeded request context and keep the context open."""
    with app.test_request_context():
        from flask import g

        seed_session()
        if handler_case.needs_character_in_context:
            mock_global_context.characters = [
                CharacterFactory.build(id=handler_case.parent_id, campaign_id="camp-456")
            ]
            g.global_context = mock_global_context
        yield handler_case.handler_class(handler_case.parent_id, **handler_case.handler_kwargs)


class TestNotesHandlerValidation:
    """Tests for validate() across all notes handlers."""

    def test_empty_title_returns_error(self, handler_case) -> None:
        """Verify validation rejects an empty title."""
        # Given a handler instance with no service dependency
        handler = handler_case.handler_class.__new__(handler_case.handler_class)

        # When validating form data with an empty title
        errors = handler.validate({"title": "", "content": "Some content"})

        # Then a title error is returned
        assert errors["title"] == "Title is required"

    def test_empty_content_returns_error(self, handler_case) -> None:
        """Verify validation rejects empty content."""
        # Given a handler instance with no service dependency
        handler = handler_case.handler_class.__new__(handler_case.handler_class)

        # When validating form data with empty content
        errors = handler.validate({"title": "A Title", "content": ""})

        # Then a content error is returned
        assert errors["content"] == "Content is required"

    def test_whitespace_only_fields_return_errors(self, handler_case) -> None:
        """Verify validation rejects whitespace-only fields."""
        # Given a handler instance with no service dependency
        handler = handler_case.handler_class.__new__(handler_case.handler_class)

        # When validating form data with whitespace-only values
        errors = handler.validate({"title": "   ", "content": "  \t  "})

        # Then both errors are returned
        assert errors["title"] == "Title is required"
        assert errors["content"] == "Content is required"

    def test_valid_data_returns_no_errors(self, handler_case) -> None:
        """Verify validation accepts valid form data."""
        # Given a handler instance with no service dependency
        handler = handler_case.handler_class.__new__(handler_case.handler_class)

        # When validating valid form data
        errors = handler.validate({"title": "My Title", "content": "My content"})

        # Then no errors are returned
        assert errors == {}


class TestNotesHandlerOperations:
    """Tests for the shared CRUD operations across all notes handlers."""

    def test_list_items_calls_service(self, handler_case, handler_in_context, fake_vclient) -> None:
        """Verify list_items fetches the parent's notes from the API."""
        # When listing items
        handler_in_context.list_items()

        # Then the parent's notes are requested
        fake_vclient.assert_called(handler_case.list_route, params=handler_case.path_params)

    def test_get_item_calls_service(self, handler_case, handler_in_context, fake_vclient) -> None:
        """Verify get_item fetches the note under the parent from the API."""
        # When getting a single item
        handler_in_context.get_item("note-789")

        # Then the note is requested under its parent
        fake_vclient.assert_called(
            handler_case.get_route,
            params={**handler_case.path_params, "note_id": "note-789"},
            times=1,
        )

    def test_create_item_strips_whitespace(
        self, handler_case, handler_in_context, fake_vclient
    ) -> None:
        """Verify create_item strips whitespace from form values before sending to the API."""
        # When creating an item with padded whitespace
        handler_in_context.create_item({"title": "  My Title  ", "content": "  My Content  "})

        # Then the API receives stripped values under the parent
        fake_vclient.assert_called(
            handler_case.create_route,
            params=handler_case.path_params,
            json={"title": "My Title", "content": "My Content"},
            times=1,
        )

    def test_update_item_strips_whitespace(
        self, handler_case, handler_in_context, fake_vclient
    ) -> None:
        """Verify update_item strips whitespace from form values before sending to the API."""
        # When updating with padded whitespace
        handler_in_context.update_item("note-789", {"title": "  Updated  ", "content": "  New  "})

        # Then the API receives stripped values for that note
        fake_vclient.assert_called(
            handler_case.update_route,
            params={**handler_case.path_params, "note_id": "note-789"},
            json={"title": "Updated", "content": "New"},
            times=1,
        )

    def test_delete_item_calls_service(
        self, handler_case, handler_in_context, fake_vclient
    ) -> None:
        """Verify delete_item deletes the note under the parent through the API."""
        # When deleting an item
        handler_in_context.delete_item("note-789")

        # Then the API receives a delete for that note
        fake_vclient.assert_called(
            handler_case.delete_route,
            params={**handler_case.path_params, "note_id": "note-789"},
            times=1,
        )


class TestBookNotesHandlerSpecific:
    """Tests for behavior unique to BookNotesHandler."""

    def test_list_items_returns_notes(self, app, fake_vclient) -> None:
        """Verify list_items returns the notes from the service."""
        with app.test_request_context():
            seed_session()

            notes = NoteFactory.batch(3)
            fake_vclient.set_response(Routes.BOOKS_NOTES_LIST, items=notes)

            handler = BookNotesHandler("book-123", campaign_id="camp-456")

            result = handler.list_items()

            assert result == notes

    def test_init_raises_without_campaign_id(self, app, fake_vclient) -> None:
        """Verify constructor raises ValueError when campaign_id is missing."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="campaign_id is required"):
                BookNotesHandler("book-123")

    def test_init_uses_campaign_id_kwarg(self, app, fake_vclient) -> None:
        """Verify constructor uses campaign_id kwarg to create the service."""
        with app.test_request_context():
            seed_session()

            handler = BookNotesHandler("book-999", campaign_id="camp-direct")

            assert handler._parent_id == "book-999"


class TestChapterNotesHandlerInit:
    """Tests for ChapterNotesHandler constructor validation."""

    def test_missing_campaign_id_raises_value_error(self, app, fake_vclient) -> None:
        """Verify constructor raises ValueError when campaign_id is missing."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123", book_id="book-456")

    def test_missing_book_id_raises_value_error(self, app, fake_vclient) -> None:
        """Verify constructor raises ValueError when book_id is missing."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123", campaign_id="camp-456")

    def test_missing_both_raises_value_error(self, app, fake_vclient) -> None:
        """Verify constructor raises ValueError when both campaign_id and book_id are missing."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123")

    def test_init_calls_service_with_correct_args(self, app, fake_vclient) -> None:
        """Verify the handler scopes its requests to the campaign, book, and session user."""
        with app.test_request_context():
            seed_session()

            # When listing notes through a chapter handler
            handler = ChapterNotesHandler("chapter-123", campaign_id="camp-456", book_id="book-789")
            handler.list_items()

        # Then the request carries the campaign, book, company, and On-Behalf-Of user
        (request,) = fake_vclient.assert_called(
            Routes.CHAPTERS_NOTES_LIST,
            params={
                "company_id": "test-company-id",
                "campaign_id": "camp-456",
                "book_id": "book-789",
                "chapter_id": "chapter-123",
            },
            times=1,
        )
        assert request.headers["on-behalf-of"] == "test-user-id"


class TestCharacterNotesHandlerInit:
    """Tests for CharacterNotesHandler constructor validation."""

    def test_init_raises_for_unknown_character(
        self, app, mock_global_context, fake_vclient
    ) -> None:
        """Verify constructor raises ValueError for a character not in global context."""
        with app.test_request_context():
            # Given an empty characters list in global context
            from flask import g

            g.global_context = mock_global_context
            seed_session()
            mock_global_context.characters = []

            # When/Then constructing with an unknown character ID raises ValueError
            with pytest.raises(ValueError, match="Character not found"):
                CharacterNotesHandler("nonexistent-id")


CAMPAIGN_CONTENT_HANDLERS: dict[str, tuple[type, dict[str, str]]] = {
    "campaign": (CampaignNotesHandler, {}),
    "book": (BookNotesHandler, {"campaign_id": "camp-456"}),
    "chapter": (ChapterNotesHandler, {"campaign_id": "camp-456", "book_id": "book-789"}),
}


class TestCampaignContentNotesMutationGuard:
    """Tests for the can_manage_campaign mutation guard on campaign, book, and chapter notes."""

    @pytest.mark.parametrize("handler_name", sorted(CAMPAIGN_CONTENT_HANDLERS))
    @pytest.mark.parametrize(
        ("role", "expected"), [("PLAYER", False), ("STORYTELLER", True), ("ADMIN", True)]
    )
    @pytest.mark.usefixtures("fake_vclient")
    def test_can_mutate_follows_can_manage_campaign(
        self, app, handler_name, role, expected
    ) -> None:
        """Verify note writes require campaign-management permission."""
        # Given a user of the given role in a company that restricts campaign management
        handler_class, kwargs = CAMPAIGN_CONTENT_HANDLERS[handler_name]
        context = build_global_context(user_role=role)
        assert context.company.settings.permission_manage_campaign == "STORYTELLER"

        with app.test_request_context():
            from flask import g

            seed_session()
            g.global_context = context
            g.requesting_user = context.users[0]
            handler = handler_class("parent-123", **kwargs)

            # When / Then
            assert handler.can_mutate() is expected


class TestCampaignNotesRouteGuard:
    """Tests for campaign notes write routes when the user cannot manage campaigns."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("post", "/campaign/camp-1/notes/items"),
            ("post", "/campaign/camp-1/notes/items/note-1"),
            ("delete", "/campaign/camp-1/notes/items/note-1"),
        ],
    )
    def test_player_write_is_forbidden(
        self, client, mocker: MockerFixture, fake_vclient, method, path
    ) -> None:
        """Verify a player cannot create, update, or delete campaign notes."""
        # Given a player in a company that restricts campaign management
        campaign = CampaignFactory.build(id="camp-1")
        context = build_global_context(user_role="PLAYER", campaign=campaign)
        mocker.patch("vweb.lib.cache.global_context.load", return_value=context)

        # When the player sends the write directly
        response = getattr(client, method)(
            path,
            data={"title": "Note title", "content": "Note content"},
            headers={"X-CSRFToken": get_csrf(client), "HX-Request": "true"},
        )

        # Then the request is refused and no note write reaches the API
        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_NOTES_CREATE)
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_NOTES_UPDATE)
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_NOTES_DELETE)

    @pytest.mark.parametrize(
        "path", ["/campaign/camp-1/notes/items/form", "/campaign/camp-1/notes/items/form/note-1"]
    )
    @pytest.mark.usefixtures("fake_vclient")
    def test_player_form_is_forbidden(self, client, mocker: MockerFixture, path) -> None:
        """Verify a player cannot load the add or edit note form."""
        # Given a player in a company that restricts campaign management
        campaign = CampaignFactory.build(id="camp-1")
        context = build_global_context(user_role="PLAYER", campaign=campaign)
        mocker.patch("vweb.lib.cache.global_context.load", return_value=context)

        # When the player requests the form directly
        response = client.get(path, headers={"HX-Request": "true"})

        # Then the request is refused
        assert response.status_code == 403

    def test_player_table_ignores_editable_flag(
        self, client, mocker: MockerFixture, fake_vclient
    ) -> None:
        """Verify a player gets a read-only table even when the URL asks for an editable one."""
        # Given a player in a company that restricts campaign management
        campaign = CampaignFactory.build(id="camp-1")
        context = build_global_context(user_role="PLAYER", campaign=campaign)
        mocker.patch("vweb.lib.cache.global_context.load", return_value=context)
        fake_vclient.set_response(
            Routes.CAMPAIGNS_NOTES_LIST, items=[NoteFactory.build(id="note-1")]
        )

        # When the player requests the table with editable=true
        response = client.get(
            "/campaign/camp-1/notes/items?editable=true", headers={"HX-Request": "true"}
        )

        # Then no add or edit form links are rendered
        assert response.status_code == 200
        assert "/notes/items/form" not in response.get_data(as_text=True)
