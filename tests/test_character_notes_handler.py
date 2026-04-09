"""Tests for CharacterNotesHandler service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import CharacterFactory

from vweb.routes.character_view.handlers_notes import CharacterNotesHandler


@pytest.fixture
def mock_character(mock_global_context):
    """Create a factory-built character in the global context."""
    char = CharacterFactory.build(id="char-123", campaign_id="camp-456")
    mock_global_context.characters = [char]
    return char


@pytest.fixture
def mock_svc(mocker):
    """Mock the sync_characters_service for the handler module."""
    svc = MagicMock()
    mocker.patch(
        "vweb.routes.character_view.handlers_notes.sync_characters_service", return_value=svc
    )
    return svc


class TestCharacterNotesHandlerValidation:
    """Tests for CharacterNotesHandler.validate()."""

    def test_empty_title_returns_error(self) -> None:
        """Verify validation rejects an empty title."""
        # Given a handler instance with no service dependency
        handler = CharacterNotesHandler.__new__(CharacterNotesHandler)

        # When validating form data with an empty title
        errors = handler.validate({"title": "", "content": "Some content"})

        # Then a title error is returned
        assert "Title is required" in errors

    def test_empty_content_returns_error(self) -> None:
        """Verify validation rejects empty content."""
        # Given a handler instance with no service dependency
        handler = CharacterNotesHandler.__new__(CharacterNotesHandler)

        # When validating form data with empty content
        errors = handler.validate({"title": "A Title", "content": ""})

        # Then a content error is returned
        assert "Content is required" in errors

    def test_whitespace_only_fields_return_errors(self) -> None:
        """Verify validation rejects whitespace-only fields."""
        # Given a handler instance with no service dependency
        handler = CharacterNotesHandler.__new__(CharacterNotesHandler)

        # When validating form data with whitespace-only values
        errors = handler.validate({"title": "   ", "content": "  \t  "})

        # Then both errors are returned
        assert "Title is required" in errors
        assert "Content is required" in errors

    def test_valid_data_returns_no_errors(self) -> None:
        """Verify validation accepts valid form data."""
        # Given a handler instance with no service dependency
        handler = CharacterNotesHandler.__new__(CharacterNotesHandler)

        # When validating valid form data
        errors = handler.validate({"title": "My Title", "content": "My content"})

        # Then no errors are returned
        assert errors == []


class TestCharacterNotesHandlerOperations:
    """Tests for CharacterNotesHandler CRUD operations."""

    def test_list_items_calls_service(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify list_items delegates to the vclient service."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            session["company_id"] = "test-company-id"
            handler = CharacterNotesHandler("char-123")

            # When listing items
            handler.list_items()

            # Then the service is called with the parent character ID
            mock_svc.list_all_notes.assert_called_once_with("char-123")

    def test_create_item_strips_whitespace(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify create_item strips whitespace from form values before sending to the API."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            session["company_id"] = "test-company-id"
            handler = CharacterNotesHandler("char-123")

            # When creating an item with padded whitespace
            handler.create_item({"title": "  My Title  ", "content": "  My Content  "})

            # Then the service receives stripped values
            mock_svc.create_note.assert_called_once_with(
                "char-123",
                title="My Title",
                content="My Content",
            )

    def test_delete_item_calls_service(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify delete_item delegates to the vclient service."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            session["company_id"] = "test-company-id"
            handler = CharacterNotesHandler("char-123")

            # When deleting an item
            handler.delete_item("note-789")

            # Then the service is called with the correct IDs
            mock_svc.delete_note.assert_called_once_with("char-123", "note-789")

    def test_get_item_calls_service(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify get_item delegates to the vclient service."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            session["company_id"] = "test-company-id"
            handler = CharacterNotesHandler("char-123")

            # When getting a single item
            handler.get_item("note-789")

            # Then the service is called with the correct IDs
            mock_svc.get_note.assert_called_once_with("char-123", "note-789")

    def test_update_item_strips_whitespace(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify update_item strips whitespace from form values before sending to the API."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            session["company_id"] = "test-company-id"
            handler = CharacterNotesHandler("char-123")

            # When updating with padded whitespace
            handler.update_item("note-789", {"title": "  Updated  ", "content": "  New  "})

            # Then the service receives stripped values
            mock_svc.update_note.assert_called_once_with(
                "char-123",
                "note-789",
                title="Updated",
                content="New",
            )

    def test_init_raises_for_unknown_character(self, app, mock_global_context, mock_svc) -> None:
        """Verify constructor raises ValueError for a character not in global context."""
        with app.test_request_context():
            # Given an empty characters list in global context
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            session["company_id"] = "test-company-id"
            mock_global_context.characters = []

            # When/Then constructing with an unknown character ID raises ValueError
            with pytest.raises(ValueError, match="Character not found"):
                CharacterNotesHandler("nonexistent-id")
