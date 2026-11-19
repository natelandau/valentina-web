"""Tests that each kind of form shows every validation error, not only the first.

Messages come from the validators themselves, so wording changes need no test edits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.conftest import htmx_post
from tests.helpers import seed_session, setup_form_options
from vweb.api_client.testing import Routes
from vweb.lib.base_notes import BaseNotesHandler
from vweb.routes.character_create.profile_form import validate_profile
from vweb.routes.dictionary.services import validate_term

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient


def _assert_all_shown(body: str, errors: dict[str, str], expected_fields: set[str]) -> None:
    """Assert the validator flagged the expected fields and every message is in the body."""
    assert set(errors) == expected_fields
    for message in errors.values():
        assert message in body


def test_dictionary_form_shows_every_error(client: FlaskClient, fake_vclient) -> None:
    """Verify an invalid dictionary term shows each field's error and is not saved."""
    form = {"term": "", "definition": "", "link": "not-a-url", "synonyms": ""}

    response = htmx_post(client, "/dictionary/term", form)

    assert response.status_code == 200
    _assert_all_shown(response.get_data(as_text=True), validate_term(form), {"term", "link"})
    fake_vclient.assert_not_called(Routes.DICTIONARY_CREATE)


def test_crud_table_form_shows_every_error(client: FlaskClient, set_owner, fake_vclient) -> None:
    """Verify an invalid inline CRUD form (character notes) shows each error and is not saved."""
    # Given the session user's own character
    set_owner("test-user-id")
    form = {"title": "", "content": ""}

    # When posting an empty note
    response = htmx_post(client, "/character/char-123/notes/items", form)

    # Then both errors are shown and nothing is created
    assert response.status_code == 200
    errors = BaseNotesHandler.validate(None, form)  # ty:ignore[invalid-argument-type]
    _assert_all_shown(response.get_data(as_text=True), errors, {"title", "content"})
    fake_vclient.assert_not_called(Routes.CHARACTERS_NOTES_CREATE)


def test_field_level_form_shows_every_error(
    app: Flask, client: FlaskClient, mocker, use_context, fake_vclient
) -> None:
    """Verify the manual-create profile form shows an error for each invalid field."""
    # Given a campaign and form options
    campaign = use_context(user_role="PLAYER").campaigns[0]
    setup_form_options(mocker, "vweb.routes.character_create.manual_views.fetch_form_options")
    form = {"name_last": "Lovelace", "game_version": "BOGUS", "character_class": "MORTAL"}

    # When posting a profile with a missing first name and invalid game version
    response = htmx_post(client, f"/campaign/{campaign.id}/characters/profile_edit", form)

    # Then each field's error is shown and nothing is created
    assert response.status_code == 200
    with app.test_request_context():
        seed_session()
        errors = validate_profile(form)
    _assert_all_shown(response.get_data(as_text=True), errors, {"name_first", "game_version"})
    fake_vclient.assert_not_called(Routes.CHARACTERS_CREATE)
