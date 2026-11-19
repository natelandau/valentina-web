"""Tests for character_view notes CRUD table routes."""

from __future__ import annotations

import pytest

from tests.conftest import htmx_delete, htmx_post
from tests.helpers import assert_shows_error
from vweb.api_client.testing import (
    NoteFactory,
    Routes,
)

TABLE_URL = "/character/char-123/notes/items"


@pytest.fixture
def own_character(set_owner) -> None:
    """Make char-123 the requesting user's own character."""
    set_owner("test-user-id")


class TestCharacterNotesGet:
    """Tests for GET requests to character notes CRUD."""

    def test_lists_notes_from_api(self, client, own_character, fake_vclient) -> None:
        """Verify the table shows the character's notes."""
        # Given a note on the character
        fake_vclient.set_response(
            Routes.CHARACTERS_NOTES_LIST, items=[NoteFactory.build(title="Test Note")]
        )

        # When requesting the table
        response = client.get(TABLE_URL, headers={"HX-Request": "true"})

        # Then the note is listed
        assert "Test Note" in response.get_data(as_text=True)
        fake_vclient.assert_called(
            Routes.CHARACTERS_NOTES_LIST, params={"character_id": "char-123"}
        )

    def test_edit_form_is_prefilled(self, client, own_character, fake_vclient) -> None:
        """Verify the edit form carries the note's current title."""
        # Given an existing note
        fake_vclient.set_response(
            Routes.CHARACTERS_NOTES_GET,
            model=NoteFactory.build(id="note-789", title="Existing Title"),
        )

        # When requesting the edit form
        response = client.get(f"{TABLE_URL}/form/note-789", headers={"HX-Request": "true"})

        # Then the form shows the note's title
        assert "Existing Title" in response.get_data(as_text=True)


class TestCharacterNotesPost:
    """Tests for POST requests to character notes CRUD."""

    @pytest.mark.parametrize(
        ("path", "route"),
        [
            (TABLE_URL, Routes.CHARACTERS_NOTES_CREATE),
            (f"{TABLE_URL}/note-789", Routes.CHARACTERS_NOTES_UPDATE),
        ],
        ids=["create", "update"],
    )
    def test_saves_note_and_refetches(
        self, client, own_character, fake_vclient, path, route
    ) -> None:
        """Verify saving a note sends it to the API and reloads the table."""
        # When saving a note
        response = htmx_post(client, path, {"title": " New Note ", "content": "New content"})

        # Then the note is sent and the response triggers a table refetch
        fake_vclient.assert_called(
            route, json_subset={"title": "New Note", "content": "New content"}, times=1
        )
        assert 'hx-trigger="load"' in response.get_data(as_text=True)

    def test_validation_errors_return_form(self, client, own_character, fake_vclient) -> None:
        """Verify a blank note re-renders the form with errors and is not sent."""
        # When posting an empty note
        response = htmx_post(client, TABLE_URL, {"title": "", "content": ""})

        # Then the form shows errors and nothing is created
        assert_shows_error(response)
        fake_vclient.assert_not_called(Routes.CHARACTERS_NOTES_CREATE)

    def test_other_player_can_view_but_not_create(self, client, set_owner, fake_vclient) -> None:
        """Verify another player's character notes are readable but not writable."""
        # Given another player's character
        set_owner("other-user-id")

        # When viewing the table and attempting to create a note
        view = client.get(TABLE_URL, headers={"HX-Request": "true"})
        create = htmx_post(client, TABLE_URL, {"title": "X", "content": "Y"})

        # Then viewing works but the create is forbidden and never sent
        assert view.status_code == 200
        assert create.status_code == 403
        fake_vclient.assert_not_called(Routes.CHARACTERS_NOTES_CREATE)


class TestCharacterNotesDelete:
    """Tests for DELETE requests to character notes CRUD."""

    def test_delete_item_returns_refetch(self, client, own_character, fake_vclient) -> None:
        """Verify DELETE removes the note and reloads the table."""
        # When deleting a note
        response = htmx_delete(client, f"{TABLE_URL}/note-789")

        # Then the note is deleted and the table refetches
        fake_vclient.assert_called(
            Routes.CHARACTERS_NOTES_DELETE,
            params={"character_id": "char-123", "note_id": "note-789"},
            times=1,
        )
        assert 'hx-trigger="load"' in response.get_data(as_text=True)


class TestCharacterNotesApiErrors:
    """API refusals on a CRUD form tell the user what to fix."""

    def test_fixable_create_refusal_shows_reason(self, client, own_character, fake_vclient) -> None:
        """Verify a refused create re-renders the form with the API's field message."""
        fake_vclient.set_error(
            Routes.CHARACTERS_NOTES_CREATE,
            status_code=400,
            invalid_parameters=[{"field": "title", "message": "Must be at most 50 characters."}],
        )

        response = htmx_post(client, TABLE_URL, {"title": "Title", "content": "Body"})

        assert_shows_error(response)
        assert "Must be at most 50 characters." in response.get_data(as_text=True)

    def test_server_error_on_create_hides_detail(self, client, own_character, fake_vclient) -> None:
        """Verify a server error on create shows an error without the API's internal detail."""
        fake_vclient.set_error(
            Routes.CHARACTERS_NOTES_CREATE, status_code=500, detail="db exploded"
        )

        response = htmx_post(client, TABLE_URL, {"title": "Title", "content": "Body"})

        assert_shows_error(response)
        assert "db exploded" not in response.get_data(as_text=True)

    @pytest.mark.parametrize(
        ("status_code", "detail_shown"),
        [(403, True), (500, False)],
        ids=["refusal-shows-reason", "server-error-hides-detail"],
    )
    def test_delete_error_flashes(
        self, client, own_character, fake_vclient, status_code, detail_shown
    ) -> None:
        """Verify a failed delete swaps in a flash, exposing the reason only for user errors."""
        # Given the API refuses the delete
        fake_vclient.set_error(
            Routes.CHARACTERS_NOTES_DELETE, status_code=status_code, detail="api reason text"
        )

        # When deleting the note
        response = htmx_delete(client, f"{TABLE_URL}/note-789")

        # Then the flash container is swapped in, with the API's reason only for a refusal
        body = response.get_data(as_text=True)
        assert 'id="flash-messages" hx-swap-oob="true"' in body
        assert ("api reason text" in body) is detail_shown
