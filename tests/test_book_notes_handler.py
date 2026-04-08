"""Tests for BookNotesHandler service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import NoteFactory

from vweb.routes.book.handlers import BookNotesHandler


@pytest.fixture
def mock_svc(mocker):
    """Mock the sync_books_service for the handler module."""
    svc = MagicMock()
    mocker.patch("vweb.routes.book.handlers.sync_books_service", return_value=svc)
    return svc


class TestBookNotesHandlerValidation:
    """Tests for BookNotesHandler.validate()."""

    def test_empty_title_returns_error(self) -> None:
        """Verify validation rejects an empty title."""
        handler = BookNotesHandler.__new__(BookNotesHandler)

        errors = handler.validate({"title": "", "content": "Some content"})

        assert "Title is required" in errors

    def test_empty_content_returns_error(self) -> None:
        """Verify validation rejects empty content."""
        handler = BookNotesHandler.__new__(BookNotesHandler)

        errors = handler.validate({"title": "A Title", "content": ""})

        assert "Content is required" in errors

    def test_whitespace_only_fields_return_errors(self) -> None:
        """Verify validation rejects whitespace-only fields."""
        handler = BookNotesHandler.__new__(BookNotesHandler)

        errors = handler.validate({"title": "   ", "content": "  \t  "})

        assert "Title is required" in errors
        assert "Content is required" in errors

    def test_valid_data_returns_no_errors(self) -> None:
        """Verify validation accepts valid form data."""
        handler = BookNotesHandler.__new__(BookNotesHandler)

        errors = handler.validate({"title": "My Title", "content": "My content"})

        assert errors == []


class TestBookNotesHandlerOperations:
    """Tests for BookNotesHandler CRUD operations."""

    def test_list_items_calls_service(self, app, mock_svc) -> None:
        """Verify list_items delegates to the vclient service."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = BookNotesHandler("book-123", campaign_id="camp-456")

            handler.list_items()

            mock_svc.list_all_notes.assert_called_once_with("book-123")

    def test_list_items_returns_notes(self, app, mock_svc) -> None:
        """Verify list_items returns the notes from the service."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"

            notes = NoteFactory.batch(3)
            mock_svc.list_all_notes.return_value = notes

            handler = BookNotesHandler("book-123", campaign_id="camp-456")

            result = handler.list_items()

            assert result == notes

    def test_create_item_strips_whitespace(self, app, mock_svc) -> None:
        """Verify create_item strips whitespace from form values before sending to the API."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = BookNotesHandler("book-123", campaign_id="camp-456")

            handler.create_item({"title": "  My Title  ", "content": "  My Content  "})

            mock_svc.create_note.assert_called_once_with(
                "book-123",
                title="My Title",
                content="My Content",
            )

    def test_delete_item_calls_service(self, app, mock_svc) -> None:
        """Verify delete_item delegates to the vclient service."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = BookNotesHandler("book-123", campaign_id="camp-456")

            handler.delete_item("note-789")

            mock_svc.delete_note.assert_called_once_with("book-123", "note-789")

    def test_get_item_calls_service(self, app, mock_svc) -> None:
        """Verify get_item delegates to the vclient service."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = BookNotesHandler("book-123", campaign_id="camp-456")

            handler.get_item("note-789")

            mock_svc.get_note.assert_called_once_with("book-123", "note-789")

    def test_update_item_strips_whitespace(self, app, mock_svc) -> None:
        """Verify update_item strips whitespace from form values before sending to the API."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = BookNotesHandler("book-123", campaign_id="camp-456")

            handler.update_item("note-789", {"title": "  Updated  ", "content": "  New  "})

            mock_svc.update_note.assert_called_once_with(
                "book-123",
                "note-789",
                title="Updated",
                content="New",
            )

    def test_init_raises_without_campaign_id(self, app, mock_svc) -> None:
        """Verify constructor raises ValueError when campaign_id is missing."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"

            with pytest.raises(ValueError, match="campaign_id is required"):
                BookNotesHandler("book-123")

    def test_init_uses_campaign_id_kwarg(self, app, mock_svc) -> None:
        """Verify constructor uses campaign_id kwarg to create the service."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"

            handler = BookNotesHandler("book-999", campaign_id="camp-direct")

            assert handler._parent_id == "book-999"
