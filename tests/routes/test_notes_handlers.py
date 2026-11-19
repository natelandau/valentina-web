"""Tests for the notes CRUD handlers and the campaign, book, and chapter notes tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from tests.helpers import build_global_context, seed_session
from vweb.api_client.testing import CharacterFactory, NoteFactory, Routes
from vweb.routes.book.handlers import BookNotesHandler
from vweb.routes.campaign_notes.handlers import CampaignNotesHandler
from vweb.routes.chapter.handlers import ChapterNotesHandler
from vweb.routes.character_view.handlers_notes import CharacterNotesHandler

if TYPE_CHECKING:
    from collections.abc import Iterator

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
    """Tests for the note form rule shared by every notes handler."""

    @pytest.mark.parametrize(
        ("form_data", "invalid_fields"),
        [
            ({"title": "", "content": "Some content"}, {"title"}),
            ({"title": "A Title", "content": ""}, {"content"}),
            ({"title": "   ", "content": "  \t  "}, {"title", "content"}),
            ({"title": "My Title", "content": "My content"}, set()),
        ],
        ids=["empty-title", "empty-content", "whitespace-only", "valid"],
    )
    def test_requires_title_and_content(self, form_data, invalid_fields) -> None:
        """Verify a blank or whitespace-only title or content is an error on that field."""
        # Given a handler that needs no service to validate
        handler = BookNotesHandler.__new__(BookNotesHandler)

        # When / Then
        assert set(handler.validate(form_data)) == invalid_fields


class TestNotesHandlerOperations:
    """Tests for the shared CRUD operations across all notes handlers."""

    def test_list_items_returns_parent_notes(
        self, handler_case, handler_in_context, fake_vclient
    ) -> None:
        """Verify list_items fetches and returns the parent's notes from the API."""
        # Given notes on the parent
        notes = NoteFactory.batch(2)
        fake_vclient.set_response(handler_case.list_route, items=notes)

        # When listing items
        result = handler_in_context.list_items()

        # Then the parent's notes are requested and returned
        assert result == notes
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


class TestNotesHandlerInit:
    """Tests for the parent ids book and chapter notes handlers require."""

    @pytest.mark.parametrize(
        ("handler_class", "kwargs"),
        [
            (BookNotesHandler, {}),
            (ChapterNotesHandler, {"book_id": "book-456"}),
            (ChapterNotesHandler, {"campaign_id": "camp-456"}),
            (ChapterNotesHandler, {}),
        ],
        ids=["book-no-campaign", "chapter-no-campaign", "chapter-no-book", "chapter-no-ids"],
    )
    def test_missing_parent_id_raises(self, app, handler_class, kwargs) -> None:
        """Verify a handler without its campaign or book id refuses to build."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="required"):
                handler_class("parent-123", **kwargs)


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


@dataclass(frozen=True)
class NotesTableCase:
    """Describe one campaign-content notes table route for the shared route tests."""

    base_path: str
    path_params: dict[str, str]
    list_route: RouteSpec
    create_route: RouteSpec
    update_route: RouteSpec
    delete_route: RouteSpec


NOTES_TABLE_CASES: dict[str, NotesTableCase] = {
    "campaign": NotesTableCase(
        base_path="/campaign/camp-1/notes/items",
        path_params={"campaign_id": "camp-1"},
        list_route=Routes.CAMPAIGNS_NOTES_LIST,
        create_route=Routes.CAMPAIGNS_NOTES_CREATE,
        update_route=Routes.CAMPAIGNS_NOTES_UPDATE,
        delete_route=Routes.CAMPAIGNS_NOTES_DELETE,
    ),
    "book": NotesTableCase(
        base_path="/campaign/camp-1/book/book-1/notes",
        path_params={"campaign_id": "camp-1", "book_id": "book-1"},
        list_route=Routes.BOOKS_NOTES_LIST,
        create_route=Routes.BOOKS_NOTES_CREATE,
        update_route=Routes.BOOKS_NOTES_UPDATE,
        delete_route=Routes.BOOKS_NOTES_DELETE,
    ),
    "chapter": NotesTableCase(
        base_path="/campaign/camp-1/book/book-1/chapter/ch-1/crud-notes",
        path_params={"campaign_id": "camp-1", "book_id": "book-1", "chapter_id": "ch-1"},
        list_route=Routes.CHAPTERS_NOTES_LIST,
        create_route=Routes.CHAPTERS_NOTES_CREATE,
        update_route=Routes.CHAPTERS_NOTES_UPDATE,
        delete_route=Routes.CHAPTERS_NOTES_DELETE,
    ),
}

NOTE_WRITES = [
    pytest.param(("post", "", "create_route", {}), id="create"),
    pytest.param(("post", "/note-1", "update_route", {"note_id": "note-1"}), id="update"),
    pytest.param(("delete", "/note-1", "delete_route", {"note_id": "note-1"}), id="delete"),
]


@pytest.fixture(params=sorted(NOTES_TABLE_CASES))
def table_case(request: pytest.FixtureRequest) -> NotesTableCase:
    """Parametrize over the campaign, book, and chapter notes tables."""
    return NOTES_TABLE_CASES[request.param]


class TestNotesTableRoutes:
    """Tests for the campaign, book, and chapter notes table routes."""

    def test_table_lists_parent_notes(self, client, set_role, fake_vclient, table_case) -> None:
        """Verify the table shows the parent's notes from the API."""
        # Given a note on the parent
        set_role("PLAYER")
        fake_vclient.set_response(
            table_case.list_route, items=[NoteFactory.build(title="Remember the docks")]
        )

        # When loading the table
        response = client.get(table_case.base_path, headers={"HX-Request": "true"})

        # Then the parent's note is shown
        assert response.status_code == 200
        assert b"Remember the docks" in response.data
        fake_vclient.assert_called(table_case.list_route, params=table_case.path_params)

    @pytest.mark.parametrize("write", NOTE_WRITES)
    def test_storyteller_write_reaches_api(
        self, client, set_role, fake_vclient, table_case, write
    ) -> None:
        """Verify a storyteller's create, update, and delete reach the API under the parent."""
        method, suffix, route_name, note_params = write
        # Given a storyteller
        set_role("STORYTELLER")

        # When sending the write
        response = getattr(client, method)(
            f"{table_case.base_path}{suffix}",
            data={"title": "Note title", "content": "Note content"},
            headers={"X-CSRFToken": get_csrf(client), "HX-Request": "true"},
        )

        # Then it reaches the API for that parent
        assert response.status_code == 200
        fake_vclient.assert_called(
            getattr(table_case, route_name),
            params={**table_case.path_params, **note_params},
            times=1,
        )

    @pytest.mark.parametrize("write", NOTE_WRITES)
    def test_player_write_is_forbidden(
        self, client, set_role, fake_vclient, table_case, write
    ) -> None:
        """Verify a player cannot create, update, or delete campaign, book, or chapter notes."""
        method, suffix, route_name, _ = write
        # Given a player in a company that restricts campaign management
        set_role("PLAYER")

        # When the player sends the write directly
        response = getattr(client, method)(
            f"{table_case.base_path}{suffix}",
            data={"title": "Note title", "content": "Note content"},
            headers={"X-CSRFToken": get_csrf(client), "HX-Request": "true"},
        )

        # Then the request is refused and nothing reaches the API
        assert response.status_code == 403
        fake_vclient.assert_not_called(getattr(table_case, route_name))


class TestCampaignNotesRouteGuard:
    """Tests for the generic table rules, checked through the campaign notes table."""

    @pytest.mark.parametrize(
        "path", ["/campaign/camp-1/notes/items/form", "/campaign/camp-1/notes/items/form/note-1"]
    )
    @pytest.mark.usefixtures("fake_vclient")
    def test_player_form_is_forbidden(self, client, set_role, path) -> None:
        """Verify a player cannot load the add or edit note form."""
        # Given a player in a company that restricts campaign management
        set_role("PLAYER")

        # When the player requests the form directly
        response = client.get(path, headers={"HX-Request": "true"})

        # Then the request is refused
        assert response.status_code == 403

    def test_player_table_ignores_editable_flag(self, client, set_role, fake_vclient) -> None:
        """Verify a player gets a read-only table even when the URL asks for an editable one."""
        # Given a player in a company that restricts campaign management
        set_role("PLAYER")
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
