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
    handler.validate.return_value = {}

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
            "/character/char-123/notes/items",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Test Note" in response.data

    def test_get_add_form_returns_200(self, client, mock_notes_handler) -> None:
        """Verify GET /form returns the add form."""
        response = client.get(
            "/character/char-123/notes/items/form",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"<form" in response.data

    def test_get_edit_form_returns_200(self, client, mock_notes_handler) -> None:
        """Verify GET /form/<id> returns the edit form with populated data."""
        response = client.get(
            "/character/char-123/notes/items/form/note-789",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Test Note" in response.data


class TestCharacterNotesPost:
    """Tests for POST requests to character notes CRUD."""

    def test_create_item_returns_refetch(self, client, mock_notes_handler) -> None:
        """Verify POST creates item and returns a refetch snippet."""
        response = client.post(
            "/character/char-123/notes/items",
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
            "/character/char-123/notes/items/note-789",
            data={"title": "Updated", "content": "Updated content"},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_notes_handler.update_item.assert_called_once()

    def test_validation_errors_return_form(self, client, mock_notes_handler) -> None:
        """Verify POST with validation errors re-renders form with error messages."""
        mock_notes_handler.validate.return_value = {"title": "Title is required"}
        response = client.post(
            "/character/char-123/notes/items",
            data={"title": "", "content": ""},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        assert b"alert-error" in response.data

    def test_post_denied_when_handler_blocks_mutation(self, client, mock_notes_handler) -> None:
        """Verify a create POST is 403 when the handler disallows mutation."""
        # Given a handler that blocks mutation (restricted NPC editing)
        mock_notes_handler.can_mutate.return_value = False
        csrf = get_csrf(client)

        # When attempting to create a note
        response = client.post(
            "/character/char-123/notes/items",
            data={"title": "X", "content": "Y", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the request is forbidden and no create occurs
        assert response.status_code == 403
        mock_notes_handler.create_item.assert_not_called()

    def test_get_allowed_when_handler_blocks_mutation(self, client, mock_notes_handler) -> None:
        """Verify viewing the table is still allowed when mutation is blocked."""
        # Given a handler that blocks mutation
        mock_notes_handler.can_mutate.return_value = False

        # When requesting the table (read)
        response = client.get(
            "/character/char-123/notes/items",
            headers={"HX-Request": "true"},
        )

        # Then the table renders normally
        assert response.status_code == 200


class TestCharacterNotesDelete:
    """Tests for DELETE requests to character notes CRUD."""

    def test_delete_item_returns_refetch(self, client, mock_notes_handler) -> None:
        """Verify DELETE removes item and returns a refetch snippet."""
        response = client.delete(
            "/character/char-123/notes/items/note-789",
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_notes_handler.delete_item.assert_called_once()


class TestCharacterNotesApiErrors:
    """API refusals on a CRUD form tell the user what to fix."""

    def test_validation_error_shows_field_message(self, client, mock_notes_handler) -> None:
        """Verify an API 400 shows the field message instead of a generic error."""
        from vclient.exceptions import ValidationError

        # Given the API rejects the title's length
        mock_notes_handler.create_item.side_effect = ValidationError(
            "bad",
            400,
            {
                "detail": "Validation failed for one or more fields.",
                "invalid_parameters": [
                    {"field": "title", "message": "Must be at most 50 characters."}
                ],
            },
        )

        # When creating a note
        response = client.post(
            "/character/char-123/notes/items",
            data={"title": "x" * 60, "content": "Body"},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        # Then the form shows what to fix
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "<li>Title: Must be at most 50 characters.</li>" in body
        assert "An error occurred" not in body

    def test_server_error_keeps_generic_message(self, client, mock_notes_handler) -> None:
        """Verify a server error shows the generic message, not the API detail."""
        from vclient.exceptions import ServerError

        # Given a create that fails server-side
        mock_notes_handler.create_item.side_effect = ServerError(
            "boom", 500, {"detail": "db exploded"}
        )

        # When creating a note
        response = client.post(
            "/character/char-123/notes/items",
            data={"title": "Title", "content": "Body"},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        # Then only the generic message is shown
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "An error occurred. Please try again." in body
        assert "db exploded" not in body

    def test_delete_refusal_flashes_api_message(self, client, mock_notes_handler) -> None:
        """Verify a refused delete tells the user why, with the flash swapped in."""
        from vclient.exceptions import AuthorizationError

        # Given the API refuses the delete
        mock_notes_handler.delete_item.side_effect = AuthorizationError(
            "Forbidden", 403, {"detail": "You cannot delete this note"}
        )

        # When deleting the note
        response = client.delete(
            "/character/char-123/notes/items/note-789",
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        # Then the flash container carries the API's message
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'id="flash-messages" hx-swap-oob="true"' in body
        assert "You cannot delete this note" in body

    def test_delete_server_error_flashes_fallback(self, client, mock_notes_handler) -> None:
        """Verify a server error on delete flashes the fallback, not the API detail."""
        from vclient.exceptions import ServerError

        # Given a delete that fails server-side
        mock_notes_handler.delete_item.side_effect = ServerError(
            "boom", 500, {"detail": "db exploded"}
        )

        # When deleting the note
        response = client.delete(
            "/character/char-123/notes/items/note-789",
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        # Then only the fallback is shown
        body = response.get_data(as_text=True)
        assert "Could not delete. Please try again." in body
        assert "db exploded" not in body
