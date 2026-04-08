"""Tests for character_view notes CRUD table routes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import (
    CampaignFactory,
    CharacterFactory,
    NoteFactory,
)

from tests.conftest import get_csrf


@pytest.fixture
def _mock_character(mock_global_context) -> None:
    """Add a character to global context for CRUD tests."""
    char = CharacterFactory.build(
        id="char-123",
        campaign_id="camp-456",
        name="Test Character",
        user_player_id="test-user-id",
    )
    mock_global_context.characters = [char]
    campaign = CampaignFactory.build(id="camp-456")
    mock_global_context.campaigns = [campaign]


@pytest.fixture
def mock_notes_handler(mocker, _mock_character):
    """Mock the CRUD handler for character notes."""
    note = NoteFactory.build(id="note-789", title="Test Note", content="Test content")

    handler = MagicMock()
    handler.list_items.return_value = [note]
    handler.get_item.return_value = note
    handler.create_item.return_value = None
    handler.update_item.return_value = None
    handler.delete_item.return_value = None
    handler.validate.return_value = []

    mocker.patch(
        "vweb.routes.character_view.views_notes.CharacterNotesTableView._build_handler",
        return_value=handler,
    )
    return handler


class TestCharacterNotesGet:
    """Tests for GET requests to character notes CRUD."""

    def test_get_table_returns_200(self, client, mock_notes_handler) -> None:
        """Verify GET returns the notes table HTML."""
        response = client.get(
            "/character/char-123/notes",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Test Note" in response.data

    def test_get_add_form_returns_200(self, client, mock_notes_handler) -> None:
        """Verify GET /form returns the add form."""
        response = client.get(
            "/character/char-123/notes/form",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"<form" in response.data

    def test_get_edit_form_returns_200(self, client, mock_notes_handler) -> None:
        """Verify GET /form/<id> returns the edit form with populated data."""
        response = client.get(
            "/character/char-123/notes/form/note-789",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Test Note" in response.data


class TestCharacterNotesPost:
    """Tests for POST requests to character notes CRUD."""

    def test_create_item_returns_refetch(self, client, mock_notes_handler) -> None:
        """Verify POST creates item and returns a refetch snippet."""
        response = client.post(
            "/character/char-123/notes",
            data={"title": "New Note", "content": "New content"},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_notes_handler.create_item.assert_called_once()
        body = response.get_data(as_text=True)
        assert 'hx-trigger="load"' in body

    def test_update_item_returns_refetch(self, client, mock_notes_handler) -> None:
        """Verify POST with item_id updates and returns a refetch snippet."""
        response = client.post(
            "/character/char-123/notes/note-789",
            data={"title": "Updated", "content": "Updated content"},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_notes_handler.update_item.assert_called_once()

    def test_validation_errors_return_form(self, client, mock_notes_handler) -> None:
        """Verify POST with validation errors re-renders form with error messages."""
        mock_notes_handler.validate.return_value = ["Title is required"]
        response = client.post(
            "/character/char-123/notes",
            data={"title": "", "content": ""},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        assert b"alert-error" in response.data


class TestCharacterNotesDelete:
    """Tests for DELETE requests to character notes CRUD."""

    def test_delete_item_returns_refetch(self, client, mock_notes_handler) -> None:
        """Verify DELETE removes item and returns a refetch snippet."""
        response = client.delete(
            "/character/char-123/notes/note-789",
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_notes_handler.delete_item.assert_called_once()
