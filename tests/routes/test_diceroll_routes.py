"""Tests for dice roll routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from vclient.exceptions import RequestValidationError, ValidationError
from vclient.testing import (
    CampaignFactory,
    CharacterFactory,
    CharacterTraitFactory,
    DicerollFactory,
    Routes,
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
        """Verify GET with HX-Request returns the bare fragment, not the full page."""
        # Given a valid character
        char, _, _ = mock_diceroll_deps

        # When requesting the roll modal content
        response = client.get(
            f"/roll/{char.id}",
            headers={"HX-Request": "true"},
        )

        # Then a fragment (no PageLayout chrome) is returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"/roll/{char.id}/custom" in body
        assert "<!DOCTYPE html>" not in body
        assert "HX-Request" in (response.headers.get("Vary") or "")

    def test_returns_full_page_on_direct_navigation(
        self, client: FlaskClient, mock_diceroll_deps
    ) -> None:
        """Verify GET without HX-Request returns the full page wrapped in PageLayout."""
        # Given a valid character
        char, _, _ = mock_diceroll_deps

        # When navigating directly (no HX-Request header)
        response = client.get(f"/roll/{char.id}")

        # Then a full HTML document is returned with the form content embedded
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "<!DOCTYPE html>" in body
        assert f"/roll/{char.id}/custom" in body

    def test_back_link_uses_same_origin_referrer(
        self, client: FlaskClient, mock_diceroll_deps
    ) -> None:
        """Verify the back link points at the same-origin referrer the user came from."""
        # Given a valid character and a referer pointing at the campaign page
        char, _, _ = mock_diceroll_deps

        # When navigating to the roll page from the campaign page
        response = client.get(
            f"/roll/{char.id}",
            headers={"Referer": "http://localhost/campaigns/camp-1"},
        )

        # Then the back link reflects that origin page
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'href="http://localhost/campaigns/camp-1"' in body

    def test_back_link_falls_back_when_referrer_missing(
        self, client: FlaskClient, mock_diceroll_deps
    ) -> None:
        """Verify the back link falls back to the character page without a referrer."""
        # Given a valid character and no Referer header
        char, _, _ = mock_diceroll_deps

        # When navigating directly (no Referer)
        response = client.get(f"/roll/{char.id}")

        # Then the back link points at the character page
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f'href="/character/{char.id}"' in body

    def test_back_link_rejects_cross_origin_referrer(
        self, client: FlaskClient, mock_diceroll_deps
    ) -> None:
        """Verify a cross-origin referrer is ignored to prevent open-redirect-style links."""
        # Given a valid character and an off-site referer
        char, _, _ = mock_diceroll_deps

        # When navigating with a cross-origin Referer
        response = client.get(
            f"/roll/{char.id}",
            headers={"Referer": "http://evil.example.com/phish"},
        )

        # Then the back link falls back to the character page, not the off-site URL
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "evil.example.com" not in body
        assert f'href="/character/{char.id}"' in body

    def test_back_link_rejects_any_roll_page_referrer(
        self, client: FlaskClient, mock_diceroll_deps
    ) -> None:
        """Verify referrers from any /roll/* page fall back (no ping-pong between roll pages)."""
        # Given a valid character
        char, _, _ = mock_diceroll_deps

        # When the referrer is another character's roll page
        response = client.get(
            f"/roll/{char.id}",
            headers={"Referer": "http://localhost/roll/other-char-id"},
        )

        # Then the back link falls back to the character page, not the other roll page
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "/roll/other-char-id" not in body
        assert f'href="/character/{char.id}"' in body

    def test_back_link_rejects_self_referrer(self, client: FlaskClient, mock_diceroll_deps) -> None:
        """Verify a referrer pointing at the roll page itself doesn't loop the user back."""
        # Given a valid character and a referer pointing at the roll page
        char, _, _ = mock_diceroll_deps

        # When the referrer is the roll page itself (e.g. after a refresh)
        response = client.get(
            f"/roll/{char.id}",
            headers={"Referer": f"http://localhost/roll/{char.id}"},
        )

        # Then the back link falls back to the character page
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f'href="/character/{char.id}"' in body

    def test_back_link_rejects_javascript_scheme(
        self, client: FlaskClient, mock_diceroll_deps
    ) -> None:
        """Verify a javascript: referrer cannot reach the rendered Back link."""
        # Given a valid character and a hostile Referer header
        char, _, _ = mock_diceroll_deps

        # When the referrer uses a dangerous URL scheme
        response = client.get(
            f"/roll/{char.id}",
            headers={"Referer": "javascript:alert(1)"},
        )

        # Then the dangerous scheme is dropped and Back falls back to the character page
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "javascript:" not in body
        assert f'href="/character/{char.id}"' in body

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


class _Roll(BaseModel):
    num_dice: int = Field(le=100)


def _post(client, path: str, data: dict[str, str]) -> str:
    csrf = get_csrf(client)
    response = client.post(path, data=data, headers={"HX-Request": "true", "X-CSRFToken": csrf})
    assert response.status_code == 200
    return response.get_data(as_text=True)


class TestDiceRollApiErrors:
    """API refusals show their reason, and server errors show a generic message."""

    def test_custom_roll_shows_field_message(self, client, mock_diceroll_deps, mocker) -> None:
        """Verify a 400 with invalid parameters renders the labeled field message."""
        # Given the API rejects num_dice
        detail = "Input should be less than or equal to 100"
        mocker.patch(
            "vweb.routes.diceroll.views.perform_custom_roll",
            side_effect=ValidationError(
                "Bad input",
                400,
                {
                    "detail": "Bad input",
                    "invalid_parameters": [{"field": "num_dice", "message": detail}],
                },
            ),
        )

        # When submitting a custom roll
        body = _post(
            client, "/roll/char-1/custom", {"dice_size": "10", "num_dice": "5", "difficulty": "6"}
        )

        # Then the field message is shown
        assert f"Num dice: {detail}" in body

    def test_trait_roll_shows_authorization_detail(
        self, client, mock_diceroll_deps, fake_vclient
    ) -> None:
        """Verify a 403 renders the API's detail."""
        # Given the API refuses the roll
        char_trait = mock_diceroll_deps[2].character_traits[0]
        fake_vclient.set_error(
            Routes.DICEROLLS_CREATE,
            status_code=403,
            detail="Only storytellers can roll for this character.",
        )

        # When submitting a trait roll
        body = _post(
            client,
            "/roll/char-1/traits",
            {"trait_one_id": char_trait.trait.id, "difficulty": "6", "num_desperation_dice": "0"},
        )

        # Then the detail is shown
        assert "Only storytellers can roll for this character." in body

    def test_quickroll_hides_server_error_detail(
        self, client, mock_diceroll_deps, fake_vclient
    ) -> None:
        """Verify a 500 renders the generic message without its detail."""
        # Given the API fails
        fake_vclient.set_error(Routes.DICEROLLS_QUICKROLL, status_code=500, detail="internal boom")

        # When submitting a quickroll
        body = _post(
            client,
            "/roll/char-1/quickroll",
            {"quickroll_id": "qr-1", "difficulty": "6", "num_desperation_dice": "0"},
        )

        # Then only the generic message is shown
        assert "Roll failed - please try again." in body
        assert "internal boom" not in body

    def test_quickroll_client_validation_error_never_renders_none(
        self, client, mock_diceroll_deps, mocker
    ) -> None:
        """Verify a client-side validation error shows its message, not None."""
        # Given the client rejects the request before sending it
        with pytest.raises(PydanticValidationError) as info:
            _Roll(num_dice=500)
        mocker.patch(
            "vweb.routes.diceroll.views.perform_quickroll",
            side_effect=RequestValidationError(info.value),
        )

        # When submitting a quickroll
        body = _post(
            client,
            "/roll/char-1/quickroll",
            {"quickroll_id": "qr-1", "difficulty": "6", "num_desperation_dice": "0"},
        )

        # Then no "None" leaks into the page text
        assert "None" not in body
        assert "Num dice" in body
