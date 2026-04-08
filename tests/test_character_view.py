"""Tests for character view routes."""

from __future__ import annotations

import pytest
from vclient.testing import CampaignFactory, CharacterFactory

from tests.conftest import get_csrf


@pytest.fixture
def mock_character():
    """Build a factory character with profile fields."""
    return CharacterFactory.build(
        id="char-123",
        name="Test Character",
        name_full="Test Character",
        name_first="Test",
        name_last="Character",
        name_nick="Testy",
        biography="A test biography",
        nature="Brave",
        demeanor="Calm",
        character_class="VAMPIRE",
        campaign_id="camp-1",
        user_player_id="test-user-id",
        concept_id=None,
        specialties=[],
        starting_points=0,
    )


@pytest.fixture
def mock_campaign():
    """Build a factory campaign."""
    return CampaignFactory.build(id="camp-1", name="Test Campaign")


@pytest.fixture
def mock_character_lookup(mocker, mock_character, mock_campaign):
    """Mock get_character_and_campaign to return test character and campaign."""
    mocker.patch(
        "vweb.routes.character_view.views.get_character_and_campaign",
        return_value=(mock_character, mock_campaign),
    )
    return mock_character, mock_campaign


class TestCharacterDelete:
    """Tests for DELETE /character/<character_id>."""

    def test_owner_can_delete_character(self, client, mocker, mock_character_lookup) -> None:
        """Verify character owner can delete and gets HX-Redirect to home."""
        # Given a mocked vclient delete
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mocker.patch("vweb.routes.character_view.views.clear_global_context_cache")

        csrf = get_csrf(client)

        # When sending a delete request
        response = client.delete(
            f"/character/{char.id}",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response redirects to home and delete was called
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/"
        mock_svc.delete.assert_called_once_with(char.id)

    def test_non_owner_gets_403(self, client, mocker, mock_campaign) -> None:
        """Verify non-owner cannot delete a character."""
        # Given a character owned by a different user
        char = CharacterFactory.build(
            id="char-123",
            user_player_id="different-user-id",
            campaign_id="camp-1",
        )
        mocker.patch(
            "vweb.routes.character_view.views.get_character_and_campaign",
            return_value=(char, mock_campaign),
        )

        csrf = get_csrf(client)

        # When a non-owner sends a delete request
        response = client.delete(
            f"/character/{char.id}",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_not_found_gets_403(self, client, mocker) -> None:
        """Verify delete returns 403 when character not found."""
        # Given no character found
        mocker.patch(
            "vweb.routes.character_view.views.get_character_and_campaign",
            return_value=(None, None),
        )

        csrf = get_csrf(client)

        # When deleting a nonexistent character
        response = client.delete(
            "/character/bad-id",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_clears_cache_on_delete(self, client, mocker, mock_character_lookup) -> None:
        """Verify global context cache is cleared after deletion."""
        # Given a mocked vclient delete
        char, _ = mock_character_lookup
        mocker.patch("vweb.routes.character_view.views.sync_characters_service")
        mock_clear = mocker.patch("vweb.routes.character_view.views.clear_global_context_cache")

        csrf = get_csrf(client)

        # When deleting a character
        client.delete(
            f"/character/{char.id}",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the cache is cleared
        mock_clear.assert_called_once()


class TestCharacterSectionGet:
    """Tests for GET /character/<id>/<section> via HTMX."""

    def test_htmx_section_returns_content_and_oob_nav(self, client, mock_character_lookup) -> None:
        """Verify HTMX section request returns section content and OOB CharacterNav."""
        # Given a valid character
        char, _ = mock_character_lookup

        # When requesting a section via HTMX
        response = client.get(
            f"/character/{char.id}/info",
            headers={"HX-Request": "true"},
        )

        # Then the response contains the section content and OOB nav
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'id="character-nav"' in body
        assert 'hx-swap-oob="true"' in body
