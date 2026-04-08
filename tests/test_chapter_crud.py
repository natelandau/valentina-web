"""Tests for chapter notes CRUD table routes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import NoteFactory

from tests.conftest import get_csrf


@pytest.fixture
def mock_chapter_notes_handler(mocker):
    """Mock the CRUD handler for chapter notes."""
    note = NoteFactory.build(id="note-1", title="Chapter Note", content="Content")

    handler = MagicMock()
    handler.list_items.return_value = [note]
    handler.get_item.return_value = note
    handler.create_item.return_value = None
    handler.update_item.return_value = None
    handler.delete_item.return_value = None
    handler.validate.return_value = []

    mocker.patch(
        "vweb.routes.chapter.views_notes.ChapterNotesTableView._build_handler",
        return_value=handler,
    )
    return handler


class TestChapterNotesCrud:
    """Tests for chapter notes CRUD operations."""

    def test_get_table_returns_200(self, client, mock_chapter_notes_handler) -> None:
        """Verify GET returns the chapter notes table."""
        response = client.get(
            "/campaign/camp-1/book/book-1/chapter/ch-1/crud-notes",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Chapter Note" in response.data

    def test_create_returns_refetch(self, client, mock_chapter_notes_handler) -> None:
        """Verify POST creates item and returns refetch snippet."""
        response = client.post(
            "/campaign/camp-1/book/book-1/chapter/ch-1/crud-notes",
            data={"title": "New", "content": "New"},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_chapter_notes_handler.create_item.assert_called_once()

    def test_delete_returns_refetch(self, client, mock_chapter_notes_handler) -> None:
        """Verify DELETE removes item and returns refetch snippet."""
        response = client.delete(
            "/campaign/camp-1/book/book-1/chapter/ch-1/crud-notes/note-1",
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_chapter_notes_handler.delete_item.assert_called_once()
