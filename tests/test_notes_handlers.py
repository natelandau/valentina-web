"""Tests for the notes CRUD handlers (book, chapter, character)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.testing import CharacterFactory, NoteFactory

from tests.helpers import seed_session
from vweb.routes.book.handlers import BookNotesHandler
from vweb.routes.chapter.handlers import ChapterNotesHandler
from vweb.routes.character_view.handlers_notes import CharacterNotesHandler

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture


@dataclass(frozen=True)
class NotesHandlerCase:
    """Describe one notes handler variant for the shared validation and CRUD tests."""

    handler_class: type
    service_path: str
    parent_id: str
    handler_kwargs: dict[str, str] = field(default_factory=dict)
    needs_character_in_context: bool = False


NOTES_HANDLER_CASES: dict[str, NotesHandlerCase] = {
    "book": NotesHandlerCase(
        handler_class=BookNotesHandler,
        service_path="vweb.routes.book.handlers.sync_books_service",
        parent_id="book-123",
        handler_kwargs={"campaign_id": "camp-456"},
    ),
    "chapter": NotesHandlerCase(
        handler_class=ChapterNotesHandler,
        service_path="vweb.routes.chapter.handlers.sync_chapters_service",
        parent_id="chapter-123",
        handler_kwargs={"campaign_id": "camp-456", "book_id": "book-789"},
    ),
    "character": NotesHandlerCase(
        handler_class=CharacterNotesHandler,
        service_path="vweb.routes.character_view.handlers_notes.sync_characters_service",
        parent_id="char-123",
        needs_character_in_context=True,
    ),
}


@pytest.fixture(params=sorted(NOTES_HANDLER_CASES))
def handler_case(request: pytest.FixtureRequest) -> NotesHandlerCase:
    """Parametrize over the three notes handler variants."""
    return NOTES_HANDLER_CASES[request.param]


@pytest.fixture
def mock_svc(mocker: MockerFixture, handler_case: NotesHandlerCase) -> MagicMock:
    """Mock the vclient service factory for the handler under test."""
    svc = MagicMock()
    mocker.patch(handler_case.service_path, return_value=svc)
    return svc


@pytest.fixture
def handler_in_context(app, handler_case, mock_global_context, mock_svc) -> Iterator[object]:
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
        assert "Title is required" in errors

    def test_empty_content_returns_error(self, handler_case) -> None:
        """Verify validation rejects empty content."""
        # Given a handler instance with no service dependency
        handler = handler_case.handler_class.__new__(handler_case.handler_class)

        # When validating form data with empty content
        errors = handler.validate({"title": "A Title", "content": ""})

        # Then a content error is returned
        assert "Content is required" in errors

    def test_whitespace_only_fields_return_errors(self, handler_case) -> None:
        """Verify validation rejects whitespace-only fields."""
        # Given a handler instance with no service dependency
        handler = handler_case.handler_class.__new__(handler_case.handler_class)

        # When validating form data with whitespace-only values
        errors = handler.validate({"title": "   ", "content": "  \t  "})

        # Then both errors are returned
        assert "Title is required" in errors
        assert "Content is required" in errors

    def test_valid_data_returns_no_errors(self, handler_case) -> None:
        """Verify validation accepts valid form data."""
        # Given a handler instance with no service dependency
        handler = handler_case.handler_class.__new__(handler_case.handler_class)

        # When validating valid form data
        errors = handler.validate({"title": "My Title", "content": "My content"})

        # Then no errors are returned
        assert errors == []


class TestNotesHandlerOperations:
    """Tests for the shared CRUD operations across all notes handlers."""

    def test_list_items_calls_service(self, handler_case, handler_in_context, mock_svc) -> None:
        """Verify list_items delegates to the vclient service."""
        # When listing items
        handler_in_context.list_items()

        # Then the service is called with the parent ID
        mock_svc.list_all_notes.assert_called_once_with(handler_case.parent_id)

    def test_get_item_calls_service(self, handler_case, handler_in_context, mock_svc) -> None:
        """Verify get_item delegates to the vclient service."""
        # When getting a single item
        handler_in_context.get_item("note-789")

        # Then the service is called with the correct IDs
        mock_svc.get_note.assert_called_once_with(handler_case.parent_id, "note-789")

    def test_create_item_strips_whitespace(
        self, handler_case, handler_in_context, mock_svc
    ) -> None:
        """Verify create_item strips whitespace from form values before sending to the API."""
        # When creating an item with padded whitespace
        handler_in_context.create_item({"title": "  My Title  ", "content": "  My Content  "})

        # Then the service receives stripped values
        mock_svc.create_note.assert_called_once_with(
            handler_case.parent_id,
            title="My Title",
            content="My Content",
        )

    def test_update_item_strips_whitespace(
        self, handler_case, handler_in_context, mock_svc
    ) -> None:
        """Verify update_item strips whitespace from form values before sending to the API."""
        # When updating with padded whitespace
        handler_in_context.update_item("note-789", {"title": "  Updated  ", "content": "  New  "})

        # Then the service receives stripped values
        mock_svc.update_note.assert_called_once_with(
            handler_case.parent_id,
            "note-789",
            title="Updated",
            content="New",
        )

    def test_delete_item_calls_service(self, handler_case, handler_in_context, mock_svc) -> None:
        """Verify delete_item delegates to the vclient service."""
        # When deleting an item
        handler_in_context.delete_item("note-789")

        # Then the service is called with the correct IDs
        mock_svc.delete_note.assert_called_once_with(handler_case.parent_id, "note-789")


@pytest.fixture
def mock_book_svc(mocker: MockerFixture) -> MagicMock:
    """Mock the sync_books_service for the book handler module."""
    svc = MagicMock()
    mocker.patch("vweb.routes.book.handlers.sync_books_service", return_value=svc)
    return svc


class TestBookNotesHandlerSpecific:
    """Tests for behavior unique to BookNotesHandler."""

    def test_list_items_returns_notes(self, app, mock_book_svc) -> None:
        """Verify list_items returns the notes from the service."""
        with app.test_request_context():
            seed_session()

            notes = NoteFactory.batch(3)
            mock_book_svc.list_all_notes.return_value = notes

            handler = BookNotesHandler("book-123", campaign_id="camp-456")

            result = handler.list_items()

            assert result == notes

    def test_init_raises_without_campaign_id(self, app, mock_book_svc) -> None:
        """Verify constructor raises ValueError when campaign_id is missing."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="campaign_id is required"):
                BookNotesHandler("book-123")

    def test_init_uses_campaign_id_kwarg(self, app, mock_book_svc) -> None:
        """Verify constructor uses campaign_id kwarg to create the service."""
        with app.test_request_context():
            seed_session()

            handler = BookNotesHandler("book-999", campaign_id="camp-direct")

            assert handler._parent_id == "book-999"


@pytest.fixture
def mock_chapter_svc(mocker: MockerFixture) -> MagicMock:
    """Mock the sync_chapters_service for the chapter handler module."""
    svc = MagicMock()
    mocker.patch("vweb.routes.chapter.handlers.sync_chapters_service", return_value=svc)
    return svc


class TestChapterNotesHandlerInit:
    """Tests for ChapterNotesHandler constructor validation."""

    def test_missing_campaign_id_raises_value_error(self, app, mock_chapter_svc) -> None:
        """Verify constructor raises ValueError when campaign_id is missing."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123", book_id="book-456")

    def test_missing_book_id_raises_value_error(self, app, mock_chapter_svc) -> None:
        """Verify constructor raises ValueError when book_id is missing."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123", campaign_id="camp-456")

    def test_missing_both_raises_value_error(self, app, mock_chapter_svc) -> None:
        """Verify constructor raises ValueError when both campaign_id and book_id are missing."""
        with app.test_request_context():
            seed_session()

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123")

    def test_init_calls_service_with_correct_args(self, app, mock_chapter_svc) -> None:
        """Verify constructor passes campaign_id and book_id to sync_chapters_service."""
        with app.test_request_context():
            from unittest.mock import patch

            seed_session()

            with patch(
                "vweb.routes.chapter.handlers.sync_chapters_service", return_value=MagicMock()
            ) as patched_svc:
                ChapterNotesHandler("chapter-123", campaign_id="camp-456", book_id="book-789")

                patched_svc.assert_called_once_with(
                    campaign_id="camp-456",
                    book_id="book-789",
                    on_behalf_of="test-user-id",
                    company_id="test-company-id",
                )


@pytest.fixture
def mock_character_svc(mocker: MockerFixture) -> MagicMock:
    """Mock the sync_characters_service for the character notes handler module."""
    svc = MagicMock()
    mocker.patch(
        "vweb.routes.character_view.handlers_notes.sync_characters_service", return_value=svc
    )
    return svc


class TestCharacterNotesHandlerInit:
    """Tests for CharacterNotesHandler constructor validation."""

    def test_init_raises_for_unknown_character(
        self, app, mock_global_context, mock_character_svc
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
