"""Tests for dice roll routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import (
    CampaignFactory,
    CharacterFactory,
    CharacterTraitFactory,
    DicerollFactory,
    TraitFactory,
)

from tests.conftest import get_csrf, make_dice_roll_result
from vweb.routes.diceroll.services import RollContext

if TYPE_CHECKING:
    from flask.testing import FlaskClient


@pytest.fixture
def mock_character():
    """Build a factory character for dice roll tests."""
    return CharacterFactory.build(
        id="char-1",
        name_full="Elena Vasquez",
        campaign_id="camp-1",
        user_player_id="test-user-id",
    )


@pytest.fixture
def mock_campaign():
    """Build a factory campaign with desperation."""
    return CampaignFactory.build(id="camp-1", name="Test Campaign", desperation=2)


@pytest.fixture
def mock_roll_context():
    """Build a minimal RollContext."""
    return RollContext(
        character_traits=[
            CharacterTraitFactory.build(value=3, trait=TraitFactory.build(name="Strength")),
            CharacterTraitFactory.build(value=2, trait=TraitFactory.build(name="Brawl")),
        ],
        quickrolls=[],
        campaign_desperation=2,
    )


@pytest.fixture
def mock_diceroll_deps(mocker, mock_character, mock_campaign, mock_roll_context):
    """Mock all dice roll route dependencies."""
    mocker.patch(
        "vweb.routes.diceroll.views.get_character_and_campaign",
        return_value=(mock_character, mock_campaign),
    )
    mocker.patch(
        "vweb.routes.diceroll.views.get_roll_context",
        return_value=mock_roll_context,
    )
    mocker.patch(
        "vweb.routes.diceroll.views.get_character_traits",
        return_value=mock_roll_context.character_traits,
    )
    return mock_character, mock_campaign, mock_roll_context


class TestDiceRollContentView:
    """Tests for GET /roll/<character_id>."""

    def test_returns_modal_content(self, client: FlaskClient, mock_diceroll_deps) -> None:
        """Verify GET returns dice roll form content."""
        # Given a valid character
        char, _, _ = mock_diceroll_deps

        # When requesting the roll modal content
        response = client.get(
            f"/roll/{char.id}",
            headers={"HX-Request": "true"},
        )

        # Then the form content is returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"/roll/{char.id}/custom" in body

    def test_returns_404_when_character_not_found(self, client: FlaskClient, mocker) -> None:
        """Verify 404 when character doesn't exist."""
        # Given no character found
        mocker.patch(
            "vweb.routes.diceroll.views.get_character_and_campaign",
            return_value=(None, None),
        )

        # When requesting the roll modal
        response = client.get(
            "/roll/nonexistent",
            headers={"HX-Request": "true"},
        )

        # Then 404 is returned
        assert response.status_code == 404


class TestDiceRollCustomView:
    """Tests for POST /roll/<character_id>/custom."""

    def test_returns_results_on_success(self, client, mock_diceroll_deps, mocker) -> None:
        """Verify custom roll returns results fragment."""
        # Given a successful roll
        mock_roll = DicerollFactory.build(result=make_dice_roll_result())
        mocker.patch(
            "vweb.routes.diceroll.views.perform_custom_roll",
            return_value=mock_roll,
        )
        csrf = get_csrf(client)

        # When submitting a custom roll
        response = client.post(
            "/roll/char-1/custom",
            data={"dice_size": "10", "num_dice": "5", "difficulty": "6"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then results are returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "3 successes" in body

    def test_returns_error_on_invalid_input(self, client, mock_diceroll_deps) -> None:
        """Verify custom roll returns error for non-numeric input."""
        csrf = get_csrf(client)

        # When submitting with bad values
        response = client.post(
            "/roll/char-1/custom",
            data={"dice_size": "abc", "num_dice": "5", "difficulty": "6"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then an error is shown
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Invalid input" in body

    def test_returns_error_on_api_failure(self, client, mock_diceroll_deps, mocker) -> None:
        """Verify custom roll handles API errors gracefully."""
        from vclient.exceptions import APIError

        mocker.patch(
            "vweb.routes.diceroll.views.perform_custom_roll",
            side_effect=APIError("Server error", status_code=500),
        )
        csrf = get_csrf(client)

        # When an API error occurs
        response = client.post(
            "/roll/char-1/custom",
            data={"dice_size": "10", "num_dice": "5", "difficulty": "6"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then an error message is shown
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Roll failed" in body


class TestDiceRollTraitsView:
    """Tests for POST /roll/<character_id>/traits."""

    def test_returns_results_on_success(self, client, mock_diceroll_deps, mocker) -> None:
        """Verify trait roll returns results fragment."""
        mock_roll = DicerollFactory.build(result=make_dice_roll_result())
        mocker.patch(
            "vweb.routes.diceroll.views.perform_trait_roll",
            return_value=mock_roll,
        )
        csrf = get_csrf(client)

        # When submitting a trait roll
        response = client.post(
            "/roll/char-1/traits",
            data={
                "trait_one_id": "trait-str",
                "difficulty": "6",
                "num_desperation_dice": "0",
            },
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then results are returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "3 successes" in body

    def test_returns_error_without_trait(self, client, mock_diceroll_deps) -> None:
        """Verify trait roll requires at least one trait."""
        csrf = get_csrf(client)

        # When submitting without a trait selection
        response = client.post(
            "/roll/char-1/traits",
            data={"difficulty": "6"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then an error is shown
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "trait must be selected" in body


class TestDiceRollQuickrollView:
    """Tests for POST /roll/<character_id>/quickroll."""

    def test_returns_results_on_success(self, client, mock_diceroll_deps, mocker) -> None:
        """Verify quickroll returns results fragment."""
        mock_roll = DicerollFactory.build(result=make_dice_roll_result())
        mocker.patch(
            "vweb.routes.diceroll.views.perform_quickroll",
            return_value=mock_roll,
        )
        csrf = get_csrf(client)

        # When submitting a quickroll
        response = client.post(
            "/roll/char-1/quickroll",
            data={"quickroll_id": "qr-123", "difficulty": "6", "num_desperation_dice": "0"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then results are returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "3 successes" in body

    def test_returns_error_without_quickroll_id(self, client, mock_diceroll_deps) -> None:
        """Verify quickroll requires a selection."""
        csrf = get_csrf(client)

        # When submitting without a quickroll selection
        response = client.post(
            "/roll/char-1/quickroll",
            data={"difficulty": "6"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then an error is shown
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "select a quickroll" in body
