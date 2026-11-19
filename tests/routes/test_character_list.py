"""Tests for the shared character-list filtering helpers."""

from __future__ import annotations

from vweb.api_client.testing import CharacterFactory
from vweb.routes.fragments_shared_cards.character_list import (
    build_filter_options,
    filter_characters,
    present_type_options,
)


class TestFilterCharacters:
    """Tests for filter_characters."""

    def test_no_filters_returns_all(self) -> None:
        """Verify falsy filters pass the roster through unchanged."""
        # Given a roster
        characters = CharacterFactory.batch(3)

        # When filtering with no criteria
        result = filter_characters(characters)

        # Then the whole roster is returned
        assert result == characters

    def test_filters_compose_across_player_class_and_type(self) -> None:
        """Verify player, class, and type filters all narrow the roster."""
        # Given characters varying by owner, class, and type
        keep = CharacterFactory.build(
            user_player_id="u-1", character_class="VAMPIRE", type="PLAYER"
        )
        wrong_owner = CharacterFactory.build(
            user_player_id="u-2", character_class="VAMPIRE", type="PLAYER"
        )
        wrong_class = CharacterFactory.build(
            user_player_id="u-1", character_class="MORTAL", type="PLAYER"
        )
        wrong_type = CharacterFactory.build(
            user_player_id="u-1", character_class="VAMPIRE", type="NPC"
        )

        # When filtering on all three dimensions
        result = filter_characters(
            [keep, wrong_owner, wrong_class, wrong_type],
            player_id="u-1",
            character_class="VAMPIRE",
            type_filter="PLAYER",
        )

        # Then only the character matching every criterion remains
        assert result == [keep]


class TestBuildFilterOptions:
    """Tests for build_filter_options."""

    def test_derives_sorted_player_and_class_options(self) -> None:
        """Verify options come from the roster, deduped and sorted."""
        # Given characters across two players and two classes
        characters = [
            CharacterFactory.build(user_player_id="u-2", character_class="VAMPIRE"),
            CharacterFactory.build(user_player_id="u-1", character_class="MORTAL"),
            CharacterFactory.build(user_player_id="u-1", character_class="VAMPIRE"),
        ]
        users_by_id = {"u-1": "Alice", "u-2": "Bob"}

        # When building options
        player_options, class_options = build_filter_options(characters, users_by_id)

        # Then players are (id, username) sorted by username and classes are sorted distinct
        assert player_options == [("u-1", "Alice"), ("u-2", "Bob")]
        assert class_options == ["MORTAL", "VAMPIRE"]


class TestPresentTypeOptions:
    """Tests for present_type_options."""

    def test_returns_present_types_in_order_with_labels(self) -> None:
        """Verify only present player-facing types are returned, in display order."""
        # Given a roster with NPC and PLAYER characters
        characters = [
            CharacterFactory.build(type="NPC"),
            CharacterFactory.build(type="PLAYER"),
        ]

        # When building type options
        options = present_type_options(characters)

        # Then PLAYER and NPC appear in display order
        assert [value for value, _ in options] == ["PLAYER", "NPC"]


class TestCharacterListView:
    """Tests for GET /campaign/<id>/characters."""

    def test_renders_and_remembers_campaign(self, client, use_context) -> None:
        """Verify the page renders and becomes the user's last-visited campaign."""
        # Given a campaign in the global context
        campaign = use_context(user_role="PLAYER").campaigns[0]

        # When opening the campaign's character list
        response = client.get(f"/campaign/{campaign.id}/characters")

        # Then the page renders and the campaign is remembered in the session
        assert response.status_code == 200
        with client.session_transaction() as sess:
            assert sess["last_campaign_id"] == campaign.id

    def test_unknown_campaign_returns_404(self, client) -> None:
        """Verify an unknown campaign returns 404."""
        # When opening a campaign that does not exist
        response = client.get("/campaign/nonexistent/characters")

        # Then 404 is returned
        assert response.status_code == 404
