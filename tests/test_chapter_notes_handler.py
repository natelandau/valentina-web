"""Tests for ChapterNotesHandler service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vweb.routes.chapter.handlers import ChapterNotesHandler


@pytest.fixture
def mock_svc(mocker):
    """Mock the sync_chapters_service for the handler module."""
    svc = MagicMock()
    mocker.patch("vweb.routes.chapter.handlers.sync_chapters_service", return_value=svc)
    return svc


class TestChapterNotesHandlerValidation:
    """Tests for ChapterNotesHandler.validate()."""

    def test_empty_title_returns_error(self) -> None:
        """Verify validation rejects an empty title."""
        handler = ChapterNotesHandler.__new__(ChapterNotesHandler)

        errors = handler.validate({"title": "", "content": "Some content"})

        assert "Title is required" in errors

    def test_empty_content_returns_error(self) -> None:
        """Verify validation rejects empty content."""
        handler = ChapterNotesHandler.__new__(ChapterNotesHandler)

        errors = handler.validate({"title": "A Title", "content": ""})

        assert "Content is required" in errors

    def test_whitespace_only_fields_return_errors(self) -> None:
        """Verify validation rejects whitespace-only fields."""
        handler = ChapterNotesHandler.__new__(ChapterNotesHandler)

        errors = handler.validate({"title": "   ", "content": "  \t  "})

        assert "Title is required" in errors
        assert "Content is required" in errors

    def test_valid_data_returns_no_errors(self) -> None:
        """Verify validation accepts valid form data."""
        handler = ChapterNotesHandler.__new__(ChapterNotesHandler)

        errors = handler.validate({"title": "My Title", "content": "My content"})

        assert errors == []


class TestChapterNotesHandlerInit:
    """Tests for ChapterNotesHandler constructor validation."""

    def test_missing_campaign_id_raises_value_error(self, app, mock_svc) -> None:
        """Verify constructor raises ValueError when campaign_id is missing."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123", book_id="book-456")

    def test_missing_book_id_raises_value_error(self, app, mock_svc) -> None:
        """Verify constructor raises ValueError when book_id is missing."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123", campaign_id="camp-456")

    def test_missing_both_raises_value_error(self, app, mock_svc) -> None:
        """Verify constructor raises ValueError when both campaign_id and book_id are missing."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"

            with pytest.raises(ValueError, match="campaign_id and book_id are required"):
                ChapterNotesHandler("chapter-123")


class TestChapterNotesHandlerOperations:
    """Tests for ChapterNotesHandler CRUD operations."""

    def test_list_items_calls_service(self, app, mock_svc) -> None:
        """Verify list_items delegates to the vclient service."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = ChapterNotesHandler("chapter-123", campaign_id="camp-456", book_id="book-789")

            handler.list_items()

            mock_svc.list_all_notes.assert_called_once_with("chapter-123")

    def test_get_item_calls_service(self, app, mock_svc) -> None:
        """Verify get_item delegates to the vclient service."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = ChapterNotesHandler("chapter-123", campaign_id="camp-456", book_id="book-789")

            handler.get_item("note-111")

            mock_svc.get_note.assert_called_once_with("chapter-123", "note-111")

    def test_create_item_strips_whitespace(self, app, mock_svc) -> None:
        """Verify create_item strips whitespace from form values before sending to the API."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = ChapterNotesHandler("chapter-123", campaign_id="camp-456", book_id="book-789")

            handler.create_item({"title": "  My Title  ", "content": "  My Content  "})

            mock_svc.create_note.assert_called_once_with(
                "chapter-123",
                title="My Title",
                content="My Content",
            )

    def test_update_item_strips_whitespace(self, app, mock_svc) -> None:
        """Verify update_item strips whitespace from form values before sending to the API."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = ChapterNotesHandler("chapter-123", campaign_id="camp-456", book_id="book-789")

            handler.update_item("note-111", {"title": "  Updated  ", "content": "  New  "})

            mock_svc.update_note.assert_called_once_with(
                "chapter-123",
                "note-111",
                title="Updated",
                content="New",
            )

    def test_delete_item_calls_service(self, app, mock_svc) -> None:
        """Verify delete_item delegates to the vclient service."""
        with app.test_request_context():
            from flask import session

            session["user_id"] = "test-user-id"
            handler = ChapterNotesHandler("chapter-123", campaign_id="camp-456", book_id="book-789")

            handler.delete_item("note-111")

            mock_svc.delete_note.assert_called_once_with("chapter-123", "note-111")

    def test_init_calls_service_with_correct_args(self, app, mock_svc) -> None:
        """Verify constructor passes campaign_id and book_id to sync_chapters_service."""
        with app.test_request_context():
            from unittest.mock import patch

            from flask import session

            session["user_id"] = "test-user-id"

            with patch(
                "vweb.routes.chapter.handlers.sync_chapters_service", return_value=MagicMock()
            ) as patched_svc:
                ChapterNotesHandler("chapter-123", campaign_id="camp-456", book_id="book-789")

                patched_svc.assert_called_once_with(
                    user_id="test-user-id",
                    campaign_id="camp-456",
                    book_id="book-789",
                )
