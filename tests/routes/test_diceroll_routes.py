"""Tests for dice roll routes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from tests.conftest import get_csrf, htmx_post, make_dice_roll_result
from vweb.api_client.exceptions import RequestValidationError
from vweb.api_client.testing import (
    CampaignFactory,
    CharacterFactory,
    CharacterTraitFactory,
    DicerollFactory,
    QuickrollFactory,
    Routes,
    TraitFactory,
)

if TYPE_CHECKING:
    from flask.testing import FlaskClient

ROLL_RESULT = "3 successes"
TRAIT_FORM = {"trait_one_id": "trait-str", "difficulty": "6", "num_desperation_dice": "0"}
QUICKROLL_FORM = {"quickroll_id": "qr-1", "difficulty": "6", "num_desperation_dice": "0"}
CUSTOM_FORM = {"dice_size": "10", "num_dice": "5", "difficulty": "6"}


@pytest.fixture(autouse=True)
def _roll_env(use_context, fake_vclient) -> None:
    """Serve a player's character with Strength 3, Brawl 2, one quickroll, and a roll result."""
    campaign = CampaignFactory.build(id="camp-1", desperation=2)
    character = CharacterFactory.build(
        id="char-1", campaign_id="camp-1", user_player_id="test-user-id"
    )
    use_context(user_role="PLAYER", campaign=campaign, characters=[character])

    fake_vclient.set_response(
        Routes.CHARACTER_TRAITS_LIST,
        items=[
            CharacterTraitFactory.build(value=3, trait=TraitFactory.build(id="trait-str")),
            CharacterTraitFactory.build(value=2, trait=TraitFactory.build(id="trait-brawl")),
        ],
    )
    fake_vclient.set_response(
        Routes.USERS_QUICKROLLS_LIST,
        items=[QuickrollFactory.build(id="qr-1", trait_ids=["trait-str"])],
    )
    roll = DicerollFactory.build(
        num_dice=5, dice_size=10, dice_modifier=0, result=make_dice_roll_result()
    )
    fake_vclient.set_response(Routes.DICEROLLS_CREATE, model=roll)
    fake_vclient.set_response(Routes.DICEROLLS_QUICKROLL, model=roll)


class TestDiceRollContentView:
    """Tests for GET /roll/<character_id>."""

    @pytest.mark.parametrize(("htmx", "full_page"), [(True, False), (False, True)])
    def test_returns_fragment_for_htmx_and_page_otherwise(
        self, client: FlaskClient, htmx, full_page
    ) -> None:
        """Verify the modal gets a bare fragment, direct navigation a full page, varying on HX."""
        headers = {"HX-Request": "true"} if htmx else {}

        response = client.get("/roll/char-1", headers=headers)

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "/roll/char-1/custom" in body
        assert ("<!DOCTYPE html>" in body) is full_page
        assert "HX-Request" in (response.headers.get("Vary") or "")

    def test_modifier_is_posted_by_traits_and_quickroll_forms_only(
        self, client: FlaskClient
    ) -> None:
        """Verify the traits and quickroll forms carry a modifier field and the custom form does not."""
        body = client.get("/roll/char-1", headers={"HX-Request": "true"}).get_data(as_text=True)

        assert body.count('name="dice_modifier"') == 2
        custom_form = body.split("/roll/char-1/custom")[1].split("</form>")[0]
        assert "dice_modifier" not in custom_form

    def test_quickroll_pools_are_attribute_escaped(self, client: FlaskClient) -> None:
        """Verify the quickroll pools JSON inside x-data is escaped, so it cannot break out."""
        body = client.get("/roll/char-1", headers={"HX-Request": "true"}).get_data(as_text=True)

        assert "&#34;qr-1&#34;: 3" in body
        assert '"qr-1":' not in body

    @pytest.mark.parametrize(
        ("referer", "expected_back"),
        [
            ("http://localhost/campaigns/camp-1", "http://localhost/campaigns/camp-1"),
            (None, "/character/char-1"),
            ("http://evil.example.com/phish", "/character/char-1"),
            ("http://localhost/roll/other-char-id", "/character/char-1"),
            ("http://localhost/roll/char-1", "/character/char-1"),
            ("javascript:alert(1)", "/character/char-1"),
        ],
        ids=["same-origin", "missing", "cross-origin", "other-roll-page", "self", "javascript"],
    )
    def test_back_link_honors_only_safe_referrers(
        self, client: FlaskClient, referer, expected_back
    ) -> None:
        """Verify Back returns to a same-origin non-roll referrer, else the character page."""
        headers = {"Referer": referer} if referer else {}

        body = client.get("/roll/char-1", headers=headers).get_data(as_text=True)

        assert f'href="{expected_back}"' in body
        if referer and referer != expected_back:
            assert referer not in body

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/roll/unknown"),
            ("post", "/roll/unknown/custom"),
            ("post", "/roll/unknown/traits"),
            ("post", "/roll/unknown/quickroll"),
        ],
    )
    def test_unknown_character_returns_404(
        self, client: FlaskClient, fake_vclient, method, path
    ) -> None:
        """Verify rolling for a character outside the company returns 404 and rolls nothing."""
        response = getattr(client, method)(
            path,
            data={**CUSTOM_FORM, **TRAIT_FORM, **QUICKROLL_FORM},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        assert response.status_code == 404
        fake_vclient.assert_not_called(Routes.DICEROLLS_CREATE)
        fake_vclient.assert_not_called(Routes.DICEROLLS_QUICKROLL)


class TestDiceRollSubmit:
    """Tests for the custom, traits, and quickroll submit routes."""

    def test_custom_roll_sends_form_and_shows_result(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify a custom roll sends the form values and shows the API's result."""
        response = htmx_post(client, "/roll/char-1/custom", {**CUSTOM_FORM, "comment": "  ambush "})

        assert ROLL_RESULT in response.get_data(as_text=True)
        fake_vclient.assert_called(
            Routes.DICEROLLS_CREATE,
            json_subset={
                "dice_size": 10,
                "num_dice": 5,
                "difficulty": 6,
                "comment": "ambush",
                "character_id": "char-1",
                "campaign_id": "camp-1",
            },
            times=1,
        )

    def test_trait_roll_computes_pool_from_stored_traits(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify a trait roll's pool comes from the character's stored trait values."""
        response = htmx_post(
            client, "/roll/char-1/traits", {**TRAIT_FORM, "trait_two_id": "trait-brawl"}
        )

        assert ROLL_RESULT in response.get_data(as_text=True)
        fake_vclient.assert_called(
            Routes.DICEROLLS_CREATE,
            json_subset={"num_dice": 5, "trait_ids": ["trait-str", "trait-brawl"]},
            times=1,
        )

    def test_quickroll_sends_template_and_shows_result(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify a quickroll sends the chosen template and shows the API's result."""
        response = htmx_post(client, "/roll/char-1/quickroll", QUICKROLL_FORM)

        assert ROLL_RESULT in response.get_data(as_text=True)
        fake_vclient.assert_called(
            Routes.DICEROLLS_QUICKROLL,
            json_subset={"quickroll_id": "qr-1", "character_id": "char-1"},
            times=1,
        )

    @pytest.mark.parametrize(
        ("modifier", "expected"), [(1, "5d10 +1"), (-2, "5d10 -2"), (0, "5d10")]
    )
    def test_result_shows_pool_with_signed_modifier(
        self, client: FlaskClient, fake_vclient, modifier, expected
    ) -> None:
        """Verify the result shows the pool with its signed modifier, and none when zero."""
        fake_vclient.set_response(
            Routes.DICEROLLS_CREATE,
            model=DicerollFactory.build(
                num_dice=5, dice_size=10, dice_modifier=modifier, result=make_dice_roll_result()
            ),
        )

        body = htmx_post(client, "/roll/char-1/custom", CUSTOM_FORM).get_data(as_text=True)

        assert f'data-testid="dice-pool">{expected}</p>' in body

    @pytest.mark.parametrize(
        "roll",
        [
            ("/roll/char-1/traits", Routes.DICEROLLS_CREATE, TRAIT_FORM),
            ("/roll/char-1/quickroll", Routes.DICEROLLS_QUICKROLL, QUICKROLL_FORM),
        ],
        ids=["traits", "quickroll"],
    )
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ({"dice_modifier": "2"}, 2),
            ({}, 0),
            ({"dice_modifier": ""}, 0),
            ({"dice_modifier": "-3"}, -3),
        ],
        ids=["positive", "absent", "blank", "negative"],
    )
    def test_modifier_reaches_api(
        self, client: FlaskClient, fake_vclient, roll, field, expected
    ) -> None:
        """Verify the parsed modifier, defaulting to 0, reaches the API."""
        path, route, form = roll
        htmx_post(client, path, {**form, **field})

        fake_vclient.assert_called(route, json_subset={"dice_modifier": expected}, times=1)

    @pytest.mark.parametrize(
        ("path", "form"),
        [
            ("/roll/char-1/custom", {**CUSTOM_FORM, "dice_size": "abc"}),
            ("/roll/char-1/custom", {**CUSTOM_FORM, "num_dice": "five"}),
            ("/roll/char-1/traits", {"difficulty": "6"}),
            ("/roll/char-1/traits", {**TRAIT_FORM, "difficulty": "hard"}),
            ("/roll/char-1/traits", {**TRAIT_FORM, "dice_modifier": "abc"}),
            ("/roll/char-1/traits", {**TRAIT_FORM, "trait_one_id": "trait-missing"}),
            ("/roll/char-1/quickroll", {"difficulty": "6"}),
            ("/roll/char-1/quickroll", {**QUICKROLL_FORM, "dice_modifier": "abc"}),
        ],
        ids=[
            "custom-non-integer-size",
            "custom-non-integer-dice",
            "traits-no-trait",
            "traits-non-integer-difficulty",
            "traits-non-integer-modifier",
            "traits-unknown-trait",
            "quickroll-none-selected",
            "quickroll-non-integer-modifier",
        ],
    )
    def test_invalid_input_shows_error_without_rolling(
        self, client: FlaskClient, fake_vclient, path, form
    ) -> None:
        """Verify invalid input returns the results panel without a roll."""
        response = htmx_post(client, path, form)

        assert response.status_code == 200
        assert ROLL_RESULT not in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.DICEROLLS_CREATE)
        fake_vclient.assert_not_called(Routes.DICEROLLS_QUICKROLL)

    def test_unsupported_dice_size_returns_400(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a die size outside the supported set is refused."""
        response = htmx_post(client, "/roll/char-1/custom", {**CUSTOM_FORM, "dice_size": "7"})

        assert response.status_code == 400
        fake_vclient.assert_not_called(Routes.DICEROLLS_CREATE)

    def test_dice_size_disabled_by_api_options_is_refused(
        self, client: FlaskClient, fake_vclient, mocker
    ) -> None:
        """Verify a supported die size the API's options do not offer is not rolled."""
        # Given API options that offer only d10s
        options = MagicMock()
        options.gameplay.dice_size = [10]
        mocker.patch("vweb.lib.cache.options.get", return_value=options)

        # When rolling d6s
        response = htmx_post(client, "/roll/char-1/custom", {**CUSTOM_FORM, "dice_size": "6"})

        # Then nothing is rolled
        assert ROLL_RESULT not in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.DICEROLLS_CREATE)


class _Roll(BaseModel):
    num_dice: int = Field(le=100)


class TestDiceRollApiErrors:
    """API refusals show their reason, and server errors hide their detail."""

    @pytest.mark.parametrize(
        ("path", "form", "error", "shown"),
        [
            (
                "/roll/char-1/custom",
                CUSTOM_FORM,
                {
                    "status_code": 400,
                    "invalid_parameters": [{"field": "num_dice", "message": "Too many dice"}],
                },
                "Num dice: Too many dice",
            ),
            (
                "/roll/char-1/traits",
                TRAIT_FORM,
                {"status_code": 403, "detail": "Only storytellers can roll for this character."},
                "Only storytellers can roll for this character.",
            ),
        ],
        ids=["custom-field-error", "traits-refused"],
    )
    def test_fixable_refusal_shows_reason(
        self, client: FlaskClient, fake_vclient, path, form, error, shown
    ) -> None:
        """Verify a refusal the user can fix shows the API's reason instead of a result."""
        fake_vclient.set_error(Routes.DICEROLLS_CREATE, **error)

        body = htmx_post(client, path, form).get_data(as_text=True)

        assert ROLL_RESULT not in body
        assert shown in body

    def test_server_error_hides_detail(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a server error hides its detail instead of showing a result."""
        fake_vclient.set_error(Routes.DICEROLLS_QUICKROLL, status_code=500, detail="internal boom")

        body = htmx_post(client, "/roll/char-1/quickroll", QUICKROLL_FORM).get_data(as_text=True)

        assert ROLL_RESULT not in body
        assert "internal boom" not in body

    def test_client_validation_error_never_renders_none(self, client: FlaskClient, mocker) -> None:
        """Verify a request the client rejects before sending shows its message, not None."""
        # Given the client rejects the request before sending it
        with pytest.raises(PydanticValidationError) as info:
            _Roll(num_dice=500)
        mocker.patch(
            "vweb.routes.diceroll.views.perform_quickroll",
            side_effect=RequestValidationError(info.value),
        )

        # When submitting a quickroll
        body = htmx_post(client, "/roll/char-1/quickroll", QUICKROLL_FORM).get_data(as_text=True)

        # Then the field message shows and no "None" leaks into the page text
        assert "None" not in body
        assert "Num dice" in body
