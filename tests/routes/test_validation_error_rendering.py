"""Characterization tests locking in validation-error markup shown to users.

These tests assert the exact HTML rendered on invalid form input. They must
keep passing unchanged across internal refactors of the validation-error data
shape (list vs dict) — the rendered output is the contract.
"""

from __future__ import annotations

import pytest
from vclient.testing import CampaignFactory, CharacterFactory

from tests.conftest import get_csrf


class TestDictionaryCreateErrorRendering:
    """Characterize the error markup for POST /dictionary/term with invalid data."""

    def test_invalid_term_and_link_render_alert_list_in_order(self, client) -> None:
        """Verify invalid term data re-renders the form with the exact alert markup."""
        # Given invalid form data (empty term, malformed link)
        csrf = get_csrf(client)

        # When submitting the create form
        response = client.post(
            "/dictionary/term",
            data={
                "term": "",
                "definition": "",
                "link": "not-a-url",
                "synonyms": "",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then the form re-renders with the alert container and both messages in order
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert '<div class="alert alert-error mb-4" role="alert">' in body
        assert (
            "<li>Term name is required</li>"
            "<li>Link must be a valid URL (e.g. https://example.com)</li>"
        ) in body

    def test_too_short_term_renders_single_error_item(self, client) -> None:
        """Verify a too-short term renders exactly one list item with the length message."""
        # Given a term below the minimum length
        csrf = get_csrf(client)

        # When submitting the create form
        response = client.post(
            "/dictionary/term",
            data={"term": "ab", "definition": "", "link": "", "synonyms": "", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then exactly one error list item is rendered
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "<li>Term name must be at least 3 characters</li>" in body
        assert body.count("<li>") == 1


class TestCrudFormErrorRendering:
    """Characterize the CrudForm error markup via the character notes table."""

    @pytest.fixture
    def _mock_owned_character(self, mock_global_context) -> None:
        """Add a player-owned character so the real notes handler allows mutation."""
        character = CharacterFactory.build(
            id="char-123",
            campaign_id="camp-456",
            name="Test Character",
            type="PLAYER",
            user_player_id="test-user-id",
        )
        mock_global_context.characters = [character]
        mock_global_context.campaigns = [CampaignFactory.build(id="camp-456")]

    @pytest.mark.usefixtures("_mock_owned_character")
    def test_invalid_note_renders_alert_list_in_order(self, client) -> None:
        """Verify an empty note POST re-renders the CRUD form with the exact alert markup."""
        # Given invalid form data (empty title and content) and the real notes handler
        csrf = get_csrf(client)

        # When submitting the note create form
        response = client.post(
            "/character/char-123/notes/items",
            data={"title": "", "content": ""},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the form re-renders with the alert container and both messages in order
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert '<div role="alert" class="alert alert-error mb-4">' in body
        assert "<li>Title is required</li><li>Content is required</li>" in body


class TestManualCreateProfileErrorRendering:
    """Characterize field-level error markup for the manual-create profile POST."""

    def test_invalid_profile_renders_field_error_paragraphs(self, client, mocker) -> None:
        """Verify missing fields render the exact field-level error paragraphs."""
        from tests.helpers import build_global_context, setup_form_options

        # Given a campaign and form options
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        setup_form_options(
            mocker,
            "vweb.routes.character_create.manual_views.fetch_form_options",
        )
        csrf = get_csrf(client)

        # When posting a profile with a missing first name and invalid game version
        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit",
            data={
                "name_last": "Lovelace",
                "game_version": "BOGUS",
                "character_class": "MORTAL",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then field-level error paragraphs render with the exact messages
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert (
            '<p class="text-error text-sm mt-1">First name is required (min 3 characters).</p>'
            in body
        )
        assert '<p class="text-error text-sm mt-1">A valid game version is required.</p>' in body
